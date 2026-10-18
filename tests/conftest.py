"""Shared fixtures: a fake Busabase served through httpx.MockTransport.

The fake answers with response shapes trimmed from a real local
`busabase server` (0.95.x) — see `fixtures.py` — so the tools' own request
building and response mapping run unchanged, only the network is replaced.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from busabase_dify import client as client_module


@dataclass
class FakeBusabase:
    routes: dict[tuple[str, str], Callable[[httpx.Request], Any]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, path: str, reply: Any, status: int = 200) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            body = reply(_request) if callable(reply) else reply
            if isinstance(body, httpx.Response):  # a callable reply may pick its own status
                return body
            return httpx.Response(status, json=body)

        self.routes[(method, path)] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes.get((request.method, request.url.path))
        if handler is None:
            return httpx.Response(404, json={"error": f"no fake route {request.method} {request.url.path}", "code": "NOT_FOUND"})
        return handler(request)

    def last(self, method: str, path: str) -> httpx.Request:
        for request in reversed(self.requests):
            if request.method == method and request.url.path == path:
                return request
        raise AssertionError(f"{method} {path} was never requested")

    @staticmethod
    def body(request: httpx.Request) -> Any:
        return json.loads(request.content)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeBusabase:
    api = FakeBusabase()
    monkeypatch.setattr(
        client_module,
        "_default_http",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(api), timeout=timeout),
    )
    return api

