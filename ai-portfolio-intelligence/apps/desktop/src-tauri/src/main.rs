#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod secure_runtime;

use backend::BackendProcess;
use secure_runtime::{build_runtime_injection, DesktopRuntime};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

struct AppState {
    backend: BackendProcess,
    #[allow(dead_code)]
    runtime: DesktopRuntime,
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let (backend, runtime) = BackendProcess::spawn_with_retry(app.handle())?;
            let injection = build_runtime_injection(&runtime);
            let bootstrap = format!(
                "Object.defineProperty(window, '__DESKTOP_RUNTIME__', {{ value: {injection}, writable: false, configurable: false }});"
            );

            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Portfolio Analyzer")
                .inner_size(1280.0, 860.0)
                .resizable(true)
                .initialization_script(&bootstrap)
                .build()?;

            app.manage(AppState { backend, runtime });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Portfolio Analyzer")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<AppState>() {
                    state.backend.stop();
                }
            }
        });
}
