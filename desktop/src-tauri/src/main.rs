#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use tauri::Manager;

#[derive(Default)]
struct SidecarHandle {
    child: Arc<Mutex<Option<Child>>>,
}

fn resolve_session_binary() -> String {
    let sidecar = "sess";
    if cfg!(target_os = "windows") {
        format!("{sidecar}.exe")
    } else {
        sidecar.to_string()
    }
}

fn start_sidecar() -> Option<Child> {
    let binary = resolve_session_binary();
    let mut command = Command::new(binary);
    command
        .args(["serve", "--port", "8000"])
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    match command.spawn() {
        Ok(process) => Some(process),
        Err(_) => None,
    }
}

fn stop_sidecar(handle: &Arc<Mutex<Option<Child>>>) {
    let child = {
        match handle.lock() {
            Ok(mut guard) => guard.take(),
            Err(_) => return,
        }
    };

    if let Some(mut process) = child {
        let _ = process.kill();
        let _ = process.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(SidecarHandle::default())
        .setup(|app| {
            let state = app.state::<SidecarHandle>();
            let child = start_sidecar();

            match state.child.lock() {
                Ok(mut guard) => {
                    *guard = child;
                }
                Err(_) => {
                    if let Some(mut process) = child {
                        let _ = process.kill();
                        let _ = process.wait();
                    }
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let state = window.app_handle().state::<SidecarHandle>();
                stop_sidecar(&state.child);
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run app");
}
