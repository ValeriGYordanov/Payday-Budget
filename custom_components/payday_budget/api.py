"""Client for the Payday Budget add-on REST API (§6.4)."""

from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from .const import SSE_READ_TIMEOUT_SECONDS


class PaydayBudgetError(Exception):
    """Base error."""


class CannotConnect(PaydayBudgetError):
    """The add-on is unreachable."""


class InvalidAuth(PaydayBudgetError):
    """The token was rejected (401)."""


class ApiError(PaydayBudgetError):
    """The add-on returned `{code, message, field?}`; rule violations carry the rule ID."""

    def __init__(self, status: int, code: str, message: str, field: str | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.field = field


class Actor:
    """The HA user acting through the integration (T3)."""

    def __init__(self, user_id: str | None, name: str | None) -> None:
        self.user_id = user_id
        self.name = name

    def headers(self) -> dict[str, str]:
        if not self.user_id:
            return {}
        headers = {"X-Acting-User-Id": self.user_id}
        if self.name:
            headers["X-Acting-User-Name"] = self.name
        return headers


class PaydayBudgetClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str) -> None:
        self._session = session
        self._base = f"http://{host}:{port}/api/v1/"
        self._token = token

    def _headers(self, actor: Actor | None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}"}
        if actor is not None:
            headers.update(actor.headers())
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        actor: Actor | None = None,
    ) -> Any:
        query = {k: str(v) for k, v in (params or {}).items() if v is not None}
        try:
            async with self._session.request(
                method,
                self._base + path,
                params=query,
                json=json,
                headers=self._headers(actor),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise InvalidAuth
                if response.status == 204:
                    return None
                try:
                    data = await response.json(content_type=None)
                except ValueError:
                    data = {}
                if response.status >= 400:
                    data = data if isinstance(data, dict) else {}
                    raise ApiError(
                        response.status,
                        str(data.get("code", "http_error")),
                        str(data.get("message", response.reason)),
                        data.get("field"),
                    )
                return data
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def events(self) -> AsyncIterator[str]:
        """Yield SSE event names from `GET /events` until the stream ends."""
        timeout = aiohttp.ClientTimeout(total=None, sock_read=SSE_READ_TIMEOUT_SECONDS)
        try:
            async with self._session.get(
                self._base + "events", headers=self._headers(None), timeout=timeout
            ) as response:
                if response.status == 401:
                    raise InvalidAuth
                if response.status != 200:
                    raise CannotConnect(f"events: HTTP {response.status}")
                async for raw in response.content:
                    line = raw.decode(errors="replace").strip()
                    if line.startswith("event:"):
                        yield line.removeprefix("event:").strip()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err
