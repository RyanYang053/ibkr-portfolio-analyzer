"""Per-launch local session gate for the desktop sidecar API."""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.local_runtime import LocalRuntime
from app.core.network_policy import is_loopback_client


PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/health/live",
        "/version",
    }
)


class LocalSessionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        runtime: LocalRuntime,
    ) -> None:
        super().__init__(app)
        self.runtime = runtime

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        client_host = request.client.host if request.client else None
        if not is_loopback_client(client_host):
            return JSONResponse(
                status_code=403,
                content={"detail": "Non-local request rejected"},
            )

        supplied = request.headers.get("X-Local-Session")
        if not self.runtime.token_matches(supplied):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid local session"},
            )

        return await call_next(request)
