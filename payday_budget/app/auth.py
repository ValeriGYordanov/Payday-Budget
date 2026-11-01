"""Request authentication (§6.2) and the post-write `changed` event.

- From the Supervisor (Ingress, 172.30.32.2): user from `X-Remote-User-*`.
- Otherwise `Authorization: Bearer <token>`: user from `X-Acting-User-*`.
- Everything else: 401.
"""

import hmac
import json
from dataclasses import dataclass

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.events import Broadcaster
from app.users import Actor

SUPERVISOR_IP = "172.30.32.2"
INGRESS = "ingress"
TOKEN = "token"
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class AuthContext:
    source: str
    actor: Actor


def _ingress_actor(headers: Headers) -> Actor:
    user_id = headers.get("x-remote-user-id") or None
    name = headers.get("x-remote-user-display-name") or headers.get("x-remote-user-name") or None
    return Actor(user_id, name if user_id else None)


def _token_actor(headers: Headers) -> Actor:
    user_id = headers.get("x-acting-user-id") or None
    return Actor(user_id, (headers.get("x-acting-user-name") or None) if user_id else None)


def authenticate(scope: Scope, token: str) -> AuthContext | None:
    headers = Headers(scope=scope)
    client = scope.get("client")
    if client and client[0] == SUPERVISOR_IP:
        return AuthContext(INGRESS, _ingress_actor(headers))
    scheme, _, credentials = headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and hmac.compare_digest(credentials.strip(), token):
        return AuthContext(TOKEN, _token_actor(headers))
    return None


class AuthMiddleware:
    def __init__(self, app: ASGIApp, *, token: str, broadcaster: Broadcaster) -> None:
        self.app = app
        self.token = token
        self.broadcaster = broadcaster

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        context = authenticate(scope, self.token)
        if context is None:
            await _unauthorized(send)
            return
        scope.setdefault("state", {})["auth"] = context

        if scope["method"] not in _WRITE_METHODS:
            await self.app(scope, receive, send)
            return

        status = 500

        async def send_and_notify(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
                and status < 400
            ):
                self.broadcaster.publish()

        await self.app(scope, receive, send_and_notify)


async def _unauthorized(send: Send) -> None:
    body = json.dumps({"code": "unauthorized", "message": "Authentication required"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
