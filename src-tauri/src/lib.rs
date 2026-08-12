// src-tauri/src/lib.rs
use std::time::Duration;

use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

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
            let sidecar_command = app
                .shell()
                .sidecar("shaman-backend")
                .unwrap()
                .env("BACKEND_HOST", "127.0.0.1")
                .env("BACKEND_PORT", "8000");
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

            // Brief warm-up sleep before the window loads the frontend.
            // uvicorn imports torch/ultralytics which takes several
            // seconds; the frontend's first fetch hits /health and will
            // otherwise see a connection refused. 3 seconds is enough
            // on a cold start with a warm filesystem cache.
            std::thread::sleep(Duration::from_millis(3000));

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}