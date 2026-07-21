#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod secure_runtime;

use backend::BackendProcess;
use secure_runtime::{build_initialization_script, DesktopRuntime};
use serde::Serialize;
use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Seek, SeekFrom};
use std::sync::Mutex;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_notification::NotificationExt;

struct AppState {
    backend: BackendProcess,
    #[allow(dead_code)]
    runtime: DesktopRuntime,
    inbox_offset: Mutex<u64>,
}

#[derive(Serialize)]
struct InboxPollResult {
    shown: usize,
    path: String,
}

#[tauri::command]
fn poll_desktop_notifications(app: AppHandle) -> Result<InboxPollResult, String> {
    let data_dir = backend::application_support_dir();
    let inbox = data_dir.join("notifications").join("desktop_inbox.jsonl");
    if !inbox.exists() {
        return Ok(InboxPollResult {
            shown: 0,
            path: inbox.to_string_lossy().to_string(),
        });
    }

    let state = app.state::<AppState>();
    let mut offset = state
        .inbox_offset
        .lock()
        .map_err(|_| "inbox offset lock poisoned".to_string())?;

    let mut file = OpenOptions::new()
        .read(true)
        .open(&inbox)
        .map_err(|err| format!("open inbox failed: {err}"))?;
    let len = file
        .metadata()
        .map_err(|err| format!("inbox metadata failed: {err}"))?
        .len();
    if *offset > len {
        *offset = 0;
    }
    file.seek(SeekFrom::Start(*offset))
        .map_err(|err| format!("seek inbox failed: {err}"))?;

    let mut shown = 0usize;
    let reader = BufReader::new(&file);
    for line in reader.lines() {
        let line = line.map_err(|err| format!("read inbox failed: {err}"))?;
        if line.trim().is_empty() {
            continue;
        }
        let value: serde_json::Value =
            serde_json::from_str(&line).unwrap_or_else(|_| serde_json::json!({}));
        let title = value
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or("Portfolio Analyzer");
        let body = value
            .get("body")
            .and_then(|v| v.as_str())
            .or_else(|| value.get("message").and_then(|v| v.as_str()))
            .unwrap_or("Monitoring update available");
        let _ = app
            .notification()
            .builder()
            .title(title)
            .body(body)
            .show();
        shown += 1;
    }
    *offset = len;
    Ok(InboxPollResult {
        shown,
        path: inbox.to_string_lossy().to_string(),
    })
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![poll_desktop_notifications])
        .setup(|app| {
            let (backend, runtime) = BackendProcess::spawn_with_retry(app.handle())?;
            let bootstrap = build_initialization_script(&runtime);

            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Portfolio Analyzer")
                .inner_size(1280.0, 860.0)
                .resizable(true)
                .initialization_script(&bootstrap)
                .build()?;

            app.manage(AppState {
                backend,
                runtime,
                inbox_offset: Mutex::new(0),
            });
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
