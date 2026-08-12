// src-tauri/src/lib.rs
use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Best-effort TCP probe for the sidecar's HTTP port.
fn wait_for_port(host: &str, port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    let mut attempt: u32 = 0;
    while Instant::now() < deadline {
        match TcpStream::connect((host, port)) {
            Ok(stream) => {
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
                return true;
            }
            Err(_) => {
                attempt += 1;
                let sleep_ms = 50u64.saturating_add((attempt as u64) * 25).min(250);
                std::thread::sleep(Duration::from_millis(sleep_ms));
            }
        }
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Thread-safe container to hold the sidecar handle across app lifecycle
    let sidecar_child: Arc<Mutex<Option<CommandChild>>> = Arc::new(Mutex::new(None));
    let sidecar_child_exit = Arc::clone(&sidecar_child);

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
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

            let (mut rx, child) = sidecar_command
                .spawn()
                .expect("Failed to spawn FastAPI sidecar");

            // Store the child process handle so we can terminate it on exit
            *sidecar_child.lock().unwrap() = Some(child);

            // Stream backend logs / errors to the Tauri log
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
                            eprintln!("[FastAPI terminated]: {:?}", payload);
                            break;
                        }
                        _ => {}
                    }
                }
            });

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
                    "[shaman-backend] NOT ready after {:.1}s (timeout={}s).",
                    elapsed.as_secs_f64(),
                    wait_timeout.as_secs()
                );
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    // Intercept app exit and explicitly kill the sidecar process
    app.run(move |_app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(child) = sidecar_child_exit.lock().unwrap().take() {
                let _ = child.kill();
                println!("[shaman-backend] Sidecar process killed on exit.");
            }
        }
    });
}