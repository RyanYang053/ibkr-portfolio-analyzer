from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RequestContext:
    request_id: str | None = None
    actor_id: str | None = None
    tenant_id: str | None = None
    source_ip: str | None = None
    account_id: str | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)
_context_token: ContextVar[Token | None] = ContextVar("request_context_token", default=None)


def get_request_context() -> RequestContext:
    current = _request_context.get()
    if current is None:
        return RequestContext()
    return current


def activate_request_context(
    *,
    request_id: str | None = None,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    source_ip: str | None = None,
    account_id: str | None = None,
) -> str:
    resolved_request_id = request_id or str(uuid.uuid4())
    token = _request_context.set(
        RequestContext(
            request_id=resolved_request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            source_ip=source_ip,
            account_id=account_id,
        )
    )
    _context_token.set(token)
    return resolved_request_id


def bind_actor(actor_id: str, *, tenant_id: str | None = None, account_id: str | None = None) -> None:
    current = get_request_context()
    token = _request_context.set(
        RequestContext(
            request_id=current.request_id,
            actor_id=actor_id.lower(),
            tenant_id=(tenant_id or actor_id).lower(),
            source_ip=current.source_ip,
            account_id=account_id or current.account_id,
        )
    )
    _context_token.set(token)


def clear_request_context() -> None:
    token = _context_token.get()
    if token is not None:
        _request_context.reset(token)
        _context_token.set(None)


def context_as_metadata() -> dict[str, Any]:
    current = get_request_context()
    return {
        "request_id": current.request_id,
        "actor_id": current.actor_id,
        "tenant_id": current.tenant_id,
        "source_ip": current.source_ip,
        "account_id": current.account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
