"""Acting HA user (T3). Resolved by `app.auth` from the request's source (§6.2)."""

from dataclasses import dataclass
from typing import Any

from fastapi import Request


@dataclass(frozen=True)
class Actor:
    id: str | None
    name: str | None


def actor_from_request(request: Request) -> Actor:
    context: Any = getattr(request.state, "auth", None)
    return context.actor if context is not None else Actor(None, None)
