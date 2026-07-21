use rand::RngCore;

use crate::backend::find_open_port;

#[derive(Clone)]
pub struct DesktopRuntime {
    pub host: String,
    pub port: u16,
    pub session_token: String,
}

pub fn create_runtime() -> Result<DesktopRuntime, Box<dyn std::error::Error>> {
    let port = find_open_port()?;
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    let session_token = data_encoding_base64url(&bytes);

    if session_token.len() < 43 {
        return Err("generated session token too short".into());
    }

    Ok(DesktopRuntime {
        host: "127.0.0.1".into(),
        port,
        session_token,
    })
}

pub fn build_runtime_injection(runtime: &DesktopRuntime) -> String {
    // Persist into sessionStorage so full-page MPA navigations can restore the
    // loopback API base before React mounts (avoids "Starting local API…" flash).
    format!(
        r#"{{"apiBaseUrl":"http://{}:{}","sessionToken":"{}"}}"#,
        runtime.host, runtime.port, runtime.session_token
    )
}

pub fn build_initialization_script(runtime: &DesktopRuntime) -> String {
    let injection = build_runtime_injection(runtime);
    format!(
        r#"(function(){{var r={injection};Object.defineProperty(window,'__DESKTOP_RUNTIME__',{{value:r,writable:false,configurable:true}});try{{sessionStorage.setItem('__DESKTOP_RUNTIME__',JSON.stringify(r));}}catch(e){{}}}})();"#
    )
}

fn data_encoding_base64url(bytes: &[u8]) -> String {
    // URL-safe base64 without padding, similar to Python token_urlsafe(32).
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::new();
    let mut i = 0;
    while i + 3 <= bytes.len() {
        let n = ((bytes[i] as u32) << 16) | ((bytes[i + 1] as u32) << 8) | (bytes[i + 2] as u32);
        out.push(TABLE[((n >> 18) & 63) as usize] as char);
        out.push(TABLE[((n >> 12) & 63) as usize] as char);
        out.push(TABLE[((n >> 6) & 63) as usize] as char);
        out.push(TABLE[(n & 63) as usize] as char);
        i += 3;
    }
    let rem = bytes.len() - i;
    if rem == 1 {
        let n = (bytes[i] as u32) << 16;
        out.push(TABLE[((n >> 18) & 63) as usize] as char);
        out.push(TABLE[((n >> 12) & 63) as usize] as char);
    } else if rem == 2 {
        let n = ((bytes[i] as u32) << 16) | ((bytes[i + 1] as u32) << 8);
        out.push(TABLE[((n >> 18) & 63) as usize] as char);
        out.push(TABLE[((n >> 12) & 63) as usize] as char);
        out.push(TABLE[((n >> 6) & 63) as usize] as char);
    }
    out
}
