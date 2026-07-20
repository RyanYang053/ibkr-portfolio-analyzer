"""Serve the personal desktop UI from the local FastAPI process."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.core.config import is_desktop_local, settings

router = APIRouter(tags=["desktop-ui"])

UI_ROOT = Path(__file__).resolve().parents[4] / "desktop" / "ui"


def _runtime_script(request: Request) -> str:
    host = settings.local_api_host or "127.0.0.1"
    port = settings.local_api_port or request.url.port or 8765
    token = settings.local_session_token or ""
    runtime = {
        "apiBaseUrl": f"http://{host}:{port}",
        "sessionToken": token,
    }
    return (
        "<script>Object.defineProperty(window, '__DESKTOP_RUNTIME__', {"
        f"value: {json.dumps(runtime)}, writable: false, configurable: false"
        "});</script>"
    )


@router.get("/")
def desktop_home(request: Request) -> HTMLResponse:
    if not is_desktop_local():
        return HTMLResponse(
            "<p>Desktop UI is available only in DESKTOP_LOCAL mode.</p>",
            status_code=404,
        )
    index = UI_ROOT / "index.html"
    html = index.read_text(encoding="utf-8")
    html = html.replace("</head>", _runtime_script(request) + "</head>")
    return HTMLResponse(html)


@router.get("/ui/styles.css")
def desktop_styles() -> FileResponse:
    return FileResponse(UI_ROOT / "styles.css", media_type="text/css")


@router.get("/ui/app.js")
def desktop_app_js() -> FileResponse:
    return FileResponse(UI_ROOT / "app.js", media_type="application/javascript")
