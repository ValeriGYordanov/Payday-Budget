"""Add-on runtime (§6): auth, token, SSE events, discovery, entry point."""

import asyncio
import json
import logging
import os
import socket
import stat
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import __main__ as entry
from app import config, discovery
from app.api import routes
from app.events import Broadcaster
from app.main import create_app
from tests.addon.conftest import Api, Clock, make_app

# --- §6.2 auth ----------------------------------------------------------------


def _outside(api: Api) -> TestClient:
    """A client that is not the Supervisor (e.g. the HA integration)."""
    return TestClient(api.client.app)


def _bearer(api: Api) -> dict[str, str]:
    return {"Authorization": f"Bearer {api.client.app.state.token}"}  # type: ignore[attr-defined]


def test_unauthenticated_requests_get_401(api: Api) -> None:
    client = _outside(api)
    for path in ("/api/v1/settings", "/api/v1/events", "/", "/api/v1/nope"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"
    wrong = client.get("/api/v1/settings", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    assert client.post("/api/v1/budgets", json={"name": "X", "percent": 1}).status_code == 401
    assert api.get("/budgets")["items"] == []


def test_bearer_token_is_accepted(api: Api) -> None:
    response = _outside(api).get("/api/v1/settings", headers=_bearer(api))
    assert response.status_code == 200
    token = api.client.app.state.token  # type: ignore[attr-defined]
    lowercase_scheme = _outside(api).get(
        "/api/v1/settings", headers={"authorization": f"bearer {token}"}
    )
    assert lowercase_scheme.status_code == 200
    empty = _outside(api).get("/api/v1/settings", headers={"Authorization": "Bearer "})
    assert empty.status_code == 401


def test_ingress_requests_need_no_token(api: Api) -> None:
    assert api.get("/settings")["currency"] == "EUR"
    # Ingress is identified by source address, not by any header.
    spoofed = _outside(api).get("/api/v1/settings", headers={"X-Remote-User-Id": "u1"})
    assert spoofed.status_code == 401


def test_token_endpoint_is_ingress_only(api: Api) -> None:
    token = api.get("/token")["token"]
    assert token == api.client.app.state.token  # type: ignore[attr-defined]
    response = _outside(api).get("/api/v1/token", headers=_bearer(api))
    assert (response.status_code, response.json()["code"]) == (403, "forbidden")


def test_token_is_generated_once_and_private(data_dir: Path, clock: Clock) -> None:
    first = make_app(data_dir, clock)
    token = first.state.token
    first.state.engine.dispose()
    path = data_dir / "token"
    assert path.read_text() == token
    assert len(token) >= 40
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    second = make_app(data_dir, clock)
    assert second.state.token == token
    second.state.engine.dispose()


def test_api_docs_are_disabled(api: Api) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert api.client.get(path).status_code == 404


def test_ingress_placeholder_page(api: Api) -> None:
    response = api.client.get("/")
    assert response.status_code == 200
    assert "Payday Budget" in response.text


# --- SSE `changed` events --------------------------------------------------------


def test_broadcaster_fans_out_and_coalesces() -> None:
    async def main() -> None:
        broadcaster = Broadcaster()
        broadcaster.bind(asyncio.get_running_loop())
        first, second = broadcaster.subscribe(), broadcaster.subscribe()
        broadcaster.publish()
        broadcaster.publish()  # coalesced: one pending `changed` per subscriber
        assert (first.qsize(), second.qsize()) == (1, 1)
        await asyncio.to_thread(broadcaster.publish_threadsafe)
        await asyncio.sleep(0)
        assert await first.get() == "changed"
        broadcaster.unsubscribe(first)
        assert broadcaster.subscribers == 1

    asyncio.run(main())


def test_changed_is_published_after_successful_writes_only(api: Api) -> None:
    broadcaster: Any = api.client.app.state.broadcaster  # type: ignore[attr-defined]
    calls: list[str] = []
    broadcaster.publish = lambda event="changed": calls.append(event)
    api.get("/budgets")
    assert calls == []
    api.post("/budgets", {"name": "Needs", "percent": "50"})
    assert calls == ["changed"]
    api.error("POST", "/budgets", "B1", json={"name": "X", "percent": "60"})
    api.delete(f"/budgets/{api.budget_id('Needs')}")
    assert calls == ["changed", "changed"]


def test_changed_is_published_after_scheduler_runs(
    data_dir: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        Broadcaster, "publish_threadsafe", lambda self, event="changed": calls.append(event)
    )
    app = make_app(data_dir, clock)
    with TestClient(app):
        assert calls == ["changed"]  # the startup run
    app.state.engine.dispose()


@pytest.fixture
def live_server(data_dir: Path, clock: Clock) -> Iterator[tuple[str, str]]:
    """The app on a real uvicorn server (streaming needs a real connection)."""
    app = make_app(data_dir, clock)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", app.state.token
    server.should_exit = True
    thread.join(10)
    app.state.engine.dispose()


def test_sse_stream_emits_changed_after_write(
    live_server: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "SSE_KEEPALIVE_SECONDS", 0.3)
    base, token = live_server
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base, headers=headers, timeout=10) as client:
        assert (
            client.get("/api/v1/events", headers={"Authorization": "Bearer x"}).status_code == 401
        )
        with client.stream("GET", "/api/v1/events") as stream:
            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            assert "content-length" not in stream.headers  # so Ingress streams it
            lines = stream.iter_lines()
            assert next(lines) == ": connected"
            assert next(lines) == ""
            assert next(lines) == ": keepalive"
            assert next(lines) == ""
            created = client.post("/api/v1/budgets", json={"name": "Needs", "percent": "50"})
            assert created.status_code == 201
            received = []
            for line in lines:
                if line.startswith(":"):
                    continue
                received.append(line)
                if line == "":
                    break
            assert received == ["event: changed", "data: {}", ""]


# --- §6.3 discovery ----------------------------------------------------------


class _FakeSupervisor:
    """Answers POST /discovery with the queued statuses (then 200)."""

    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.requests: list[dict[str, Any]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                fake.requests.append(
                    {
                        "path": self.path,
                        "auth": self.headers["Authorization"],
                        "body": json.loads(self.rfile.read(length)),
                    }
                )
                status = fake.statuses.pop(0) if fake.statuses else 200
                body = (
                    {"result": "ok", "data": {"uuid": "abc123"}}
                    if status == 200
                    else {"result": "error", "message": "nope"}
                )
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def supervisor() -> Iterator[_FakeSupervisor]:
    fake = _FakeSupervisor([])
    yield fake
    fake.close()


def test_discovery_posts_host_port_token(supervisor: _FakeSupervisor) -> None:
    uuid = discovery.send(
        "tok",
        8099,
        supervisor_url=supervisor.url,
        supervisor_token="sup",
        host="local-payday-budget",
    )
    assert uuid == "abc123"
    (request,) = supervisor.requests
    assert request == {
        "path": "/discovery",
        "auth": "Bearer sup",
        "body": {
            "service": "payday_budget",
            "config": {"host": "local-payday-budget", "port": 8099, "token": "tok"},
        },
    }


def test_discovery_defaults_to_container_hostname(supervisor: _FakeSupervisor) -> None:
    discovery.send("tok", 8099, supervisor_url=supervisor.url, supervisor_token="sup")
    assert supervisor.requests[0]["body"]["config"]["host"] == socket.gethostname()


def test_discovery_skipped_outside_supervisor(
    supervisor: _FakeSupervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert discovery.send("tok", 8099, supervisor_url=supervisor.url) is None
    assert supervisor.requests == []


def test_discovery_retries_with_backoff(supervisor: _FakeSupervisor) -> None:
    supervisor.statuses = [500, 503]
    sleeps: list[float] = []
    uuid = discovery.send(
        "tok", 8099, supervisor_url=supervisor.url, supervisor_token="s", sleep=sleeps.append
    )
    assert uuid == "abc123"
    assert sleeps == [2.0, 4.0]
    assert len(supervisor.requests) == 3


def test_discovery_gives_up_after_retries(
    supervisor: _FakeSupervisor, caplog: pytest.LogCaptureFixture
) -> None:
    supervisor.statuses = [403] * 4
    sleeps: list[float] = []
    with caplog.at_level(logging.INFO):
        uuid = discovery.send(
            "s3cr3t-value",
            8099,
            supervisor_url=supervisor.url,
            supervisor_token="s",
            sleep=sleeps.append,
        )
    assert uuid is None
    assert sleeps == [2.0, 4.0, 8.0]
    assert "Discovery failed after 4 attempts" in caplog.text
    assert "s3cr3t-value" not in caplog.text  # the token is never logged


def test_discovery_runs_on_start_with_the_token(data_dir: Path, clock: Clock) -> None:
    announced: list[str] = []
    app = create_app(data_dir, today=lambda: clock.today, announce=announced.append)
    with TestClient(app):
        deadline = time.monotonic() + 5
        while not announced and time.monotonic() < deadline:
            time.sleep(0.01)
    assert announced == [app.state.token]
    app.state.engine.dispose()


# --- config & entry point -------------------------------------------------------------


def test_options_and_log_levels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.load_options(tmp_path) == {}
    (tmp_path / "options.json").write_text('{"log_level": "debug"}')
    assert config.load_options(tmp_path) == {"log_level": "debug"}
    assert config.LOG_LEVELS["trace"] == logging.DEBUG
    assert config.LOG_LEVELS["notice"] == logging.INFO
    assert config.LOG_LEVELS["fatal"] == logging.CRITICAL
    monkeypatch.setenv("PAYDAY_BUDGET_DATA", str(tmp_path))
    assert config.data_dir() == tmp_path
    assert config.db_path(tmp_path) == tmp_path / "payday_budget.db"


def test_entry_point_runs_uvicorn_for_the_addon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "options.json").write_text('{"log_level": "warning"}')
    monkeypatch.setenv("PAYDAY_BUDGET_DATA", str(tmp_path))
    captured: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(app=app, **kw))
    entry.main()
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8099
    assert captured["proxy_headers"] is False
    assert captured["log_level"] == logging.WARNING
    assert captured["access_log"] is False
    assert (tmp_path / "payday_budget.db").exists()
    assert (tmp_path / "token").exists()
    captured["app"].state.engine.dispose()
    assert os.environ["PAYDAY_BUDGET_DATA"] == str(tmp_path)
