"""Desktop local runtime: loopback bind, per-launch session token, data dirs."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from secrets import compare_digest, token_urlsafe


@dataclass(frozen=True)
class LocalRuntime:
    host: str
    port: int
    session_token: str
    parent_process_id: int

    def validate(self) -> None:
        if self.host not in {"127.0.0.1", "::1"}:
            raise RuntimeError("Desktop backend must bind to loopback")

        if not 1024 <= self.port <= 65535:
            raise RuntimeError("Invalid desktop backend port")

        if len(self.session_token) < 43:
            raise RuntimeError("Local session token is too short")

    def token_matches(self, supplied: str | None) -> bool:
        if supplied is None:
            return False

        return compare_digest(self.session_token, supplied)


def generate_session_token() -> str:
    """256-bit (approx) URL-safe token; never persist or log."""
    return token_urlsafe(32)


def application_support_dir(app_name: str = "PortfolioAnalyzer") -> Path:
    """OS-standard application data directory for personal local mode."""
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / app_name
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        root = Path(local) / app_name
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        root = Path(xdg) if xdg else Path.home() / ".local" / "share"
        root = root / "portfolio-analyzer"

    for sub in ("imports", "exports", "backups", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_sqlite_url(app_name: str = "PortfolioAnalyzer") -> str:
    db_path = application_support_dir(app_name) / "portfolio.db"
    return f"sqlite+pysqlite:///{db_path}"


def load_local_runtime_from_env() -> LocalRuntime | None:
    """Return LocalRuntime when desktop sidecar env is present."""
    host = os.getenv("LOCAL_API_HOST")
    port_raw = os.getenv("LOCAL_API_PORT")
    token = os.getenv("LOCAL_SESSION_TOKEN")
    if not host or not port_raw or not token:
        return None

    runtime = LocalRuntime(
        host=host,
        port=int(port_raw),
        session_token=token,
        parent_process_id=int(os.getenv("LOCAL_PARENT_PID") or "0"),
    )
    runtime.validate()
    return runtime
