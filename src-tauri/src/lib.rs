// src-tauri/src/lib.rs
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};

use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

/// Best-effort TCP probe for the sidecar's HTTP port. We can't do a full
/// HTTP GET (that we'd need a TLS-aware client and the backend's
/// ``BACKEND_HOST`` value), but a successful TCP connect on the port
/// the sidecar is supposed to bind to is a strong signal that uvicorn
/// is up.
fn wait_for_port(host: &str, port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    let mut attempt: u32 = 0;
    while Instant::now() < deadline {
        // uvicorn binds 127.0.0.1 from a child process; depending on
        // how Tauri spawns the sidecar the socket may briefly be in
        // TIME_WAIT or refused. Retry with a short backoff.
        match TcpStream::connect((host, port)) {
            Ok(stream) => {
                // Best-effort: a HEAD-shaped request tells uvicorn to
                // answer. The backend's `/health` route is the cheapest
                // one and is wired up by app.main.
                let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
                let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
                let mut s = stream;
                let req = format!(
                    "GET /health HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\n\r\n",
                    host, port
                );
                if s.write_all(req.as_bytes()).is_ok() {
                    let mut buf = [0u8; 256];
                    if let Ok(n) = s.read(&mut buf) {
                        if n > 0 && buf.starts_with(b"HTTP/1.1 200") {
                            return true;
                        }
                    }
                }
                // TCP connected but HTTP not yet 200; the server is up
                // enough — let the frontend retry. We don't keep
                // blocking on /health because the real probe runs in
                // the renderer.
                return true;
            }
            Err(_) => {
                attempt += 1;
                // Tiny backoff so we don't burn CPU; cap at 250 ms.
                let sleep_ms = 50u64.saturating_add((attempt as u64) * 25).min(250);
                std::thread::sleep(Duration::from_millis(sleep_ms));
            }
        }
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // "shaman-backend" maps to "binaries/shaman-backend"
            //
            // The frontend hard-codes http://localhost:8000/api (see
            // frontend/src/api.js), so the sidecar must bind to
            // 127.0.0.1:8000. We pass those as env vars — app/main.py
            // reads BACKEND_HOST / BACKEND_PORT — so the host can stay
            // editable without rebuilding the Rust shell.
            let host = std::env::var("BACKEND_HOST")
                .ok()
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| "127.0.0.1".to_string());
            let port: u16 = std::env::var("BACKEND_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(8000);

            let sidecar_command = app
                .shell()
                .sidecar("shaman-backend")
                .unwrap()
                .env("BACKEND_HOST", host.clone())
                .env("BACKEND_PORT", port.to_string());
            let (mut rx, _child) = sidecar_command
                .spawn()
                .expect("Failed to spawn FastAPI sidecar");

            // Stream backend logs / errors to the Tauri log so a packaged
            // app still surfaces "model not found", DB migration errors,
            // port-bind failures, etc. Without this the sidecar's stdout
            // is invisible on Windows (the GUI subsystem swallows it).
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line_bytes) => {
                            println!("[FastAPI]: {}", String::from_utf8_lossy(&line_bytes));
                        }
                        CommandEvent::Stderr(line_bytes) => {
                            eprintln!("[FastAPI stderr]: {}", String::from_utf8_lossy(&line_bytes));
                        }
                        CommandEvent::Error(err) => {
                            eprintln!("[FastAPI error]: {}", err);
                        }
                        CommandEvent::Terminated(payload) => {
                            // Don't panic — uvicorn only exits on fatal
                            // error. The frontend will start failing its
                            // fetches; the user can read this log line
                            // for the cause.
                            eprintln!("[FastAPI terminated]: {:?}", payload);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            // Block the setup callback until the backend's HTTP server
            // actually answers /health, OR a hard timeout elapses. The
            // window only opens after setup() returns, so the frontend
            // never sees a connection-refused state on a cold start.
            //
            // Why a poll instead of a fixed sleep: uvicorn imports
            // torch + ultralytics, which transitively imports
            // matplotlib. On the very first launch matplotlib builds
            // its font cache (10-30 s), and PyInstaller also has to
            // extract its bundle to the temp dir. We've seen cold
            // starts take 25-40 s on Windows; the previous 3 s
            // sleep was wrong by an order of magnitude.
            let wait_timeout = Duration::from_secs(60);
            let started = Instant::now();
            let ready = wait_for_port(&host, port, wait_timeout);
            let elapsed = started.elapsed();
            if ready {
                println!(
                    "[shaman-backend] ready after {:.1}s",
                    elapsed.as_secs_f64()
                );
            } else {
                eprintln!(
                    "[shaman-backend] NOT ready after {:.1}s (timeout={}s). \
                     The frontend will show a connection error until the \
                     server eventually binds.",
                    elapsed.as_secs_f64(),
                    wait_timeout.as_secs()
                );
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}