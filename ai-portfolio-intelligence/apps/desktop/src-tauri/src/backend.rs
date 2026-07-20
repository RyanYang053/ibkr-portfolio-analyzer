use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use tauri::AppHandle;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

use crate::secure_runtime::DesktopRuntime;

pub struct BackendProcess {
    child: Mutex<Option<CommandChild>>,
}

impl BackendProcess {
    pub fn spawn(
        app: &AppHandle,
        runtime: &DesktopRuntime,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let data_dir = application_support_dir();
        std::fs::create_dir_all(&data_dir)?;
        for sub in ["state", "imports", "exports", "backups", "logs"] {
            std::fs::create_dir_all(data_dir.join(sub))?;
        }

        // sidecar() takes the binary filename (not binaries/ prefix).
        let sidecar = app
            .shell()
            .sidecar("portfolio-api")
            .map_err(|err| format!("sidecar resolve failed: {err}"))?
            .env("DEPLOYMENT_MODE", "desktop_local")
            .env("ENVIRONMENT", "desktop")
            .env("PERSISTENCE_BACKEND", "json")
            .env("PORTFOLIO_DATA_DIR", data_dir.to_string_lossy().as_ref())
            .env("LOCAL_API_HOST", &runtime.host)
            .env("LOCAL_API_PORT", runtime.port.to_string())
            .env("LOCAL_SESSION_TOKEN", &runtime.session_token)
            .env("LOCAL_PARENT_PID", std::process::id().to_string())
            .env("DISABLE_AUTH_ENFORCEMENT", "true")
            .env("API_BIND_HOST", "127.0.0.1")
            .env("BROKER_MODE", "ibkr_readonly")
            .env("SCHEDULER_RUN_IN_API", "true");

        let (_rx, child) = sidecar
            .spawn()
            .map_err(|err| format!("sidecar spawn failed: {err}"))?;

        if let Err(error) = wait_for_health(runtime, Duration::from_secs(60)) {
            let _ = child.kill();
            return Err(error);
        }

        Ok(Self {
            child: Mutex::new(Some(child)),
        })
    }

    pub fn spawn_with_retry(
        app: &AppHandle,
    ) -> Result<(Self, DesktopRuntime), Box<dyn std::error::Error>> {
        let mut last_error: Option<String> = None;
        for _attempt in 0..10 {
            let runtime = crate::secure_runtime::create_runtime()?;
            match Self::spawn(app, &runtime) {
                Ok(process) => return Ok((process, runtime)),
                Err(error) => {
                    last_error = Some(error.to_string());
                }
            }
        }
        Err(format!(
            "Unable to start local API after retries: {}",
            last_error.unwrap_or_else(|| "unknown error".to_string())
        )
        .into())
    }

    pub fn stop(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}

fn wait_for_health(runtime: &DesktopRuntime, timeout: Duration) -> Result<(), Box<dyn std::error::Error>> {
    let host_port = format!("{}:{}", runtime.host, runtime.port);
    let started = std::time::Instant::now();
    while started.elapsed() < timeout {
        if health_ok(&host_port).unwrap_or(false) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Err("desktop API sidecar failed to become healthy".into())
}

fn health_ok(host_port: &str) -> Result<bool, Box<dyn std::error::Error>> {
    use std::io::{Read, Write};
    use std::net::TcpStream;

    let mut stream = TcpStream::connect(host_port)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    let request = format!(
        "GET /health HTTP/1.1\r\nHost: {host_port}\r\nConnection: close\r\n\r\n"
    );
    stream.write_all(request.as_bytes())?;
    let mut buf = String::new();
    stream.read_to_string(&mut buf)?;
    Ok(buf.starts_with("HTTP/1.1 200") || buf.starts_with("HTTP/1.0 200"))
}

pub fn find_open_port() -> Result<u16, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

pub fn application_support_dir() -> PathBuf {
    if let Some(override_dir) = std::env::var_os("PORTFOLIO_DATA_DIR") {
        return PathBuf::from(override_dir);
    }
    if cfg!(target_os = "macos") {
        dirs_next_home()
            .join("Library")
            .join("Application Support")
            .join("PortfolioAnalyzer")
    } else if cfg!(target_os = "windows") {
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| dirs_next_home().join("AppData").join("Local"))
            .join("PortfolioAnalyzer")
    } else {
        std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| dirs_next_home().join(".local").join("share"))
            .join("portfolio-analyzer")
    }
}

fn dirs_next_home() -> PathBuf {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}
