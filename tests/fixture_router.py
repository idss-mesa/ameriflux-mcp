"""Hermetic stand-in for the AmeriFlux API (and the other allow-listed sources).

Responses come from ``tests/fixtures/manifest.json``, written by
``scripts/record_fixtures.py`` from real traffic (GET only), filtered to the fixture
site set and with every email rewritten to ``@example.org``. The router fails the
test (``AssertionError``) on:

* a request it has no fixture for (and records it in :attr:`FixtureRouter.unexpected`);
* any POST without a fixture (the only POST ameriflux-mcp will ever send is the
  consented ``data_download`` of build step 7);
* a host or path outside the client's allow-list, or any ``paper_test/`` URL;
* an identity value (``tests.helpers.PRIVATE_VALUES``) in any request other than
  ``POST …/api/v1/data_download``.

Every request is recorded in :attr:`FixtureRouter.calls`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote_plus, urlencode

import httpx

from ameriflux_mcp.ameriflux.client import ALLOWED, DENIED_FRAGMENTS

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = FIXTURES / "manifest.json"
DATA_DOWNLOAD_PATH = "/api/v1/data_download"
#: The fixture site set (RESEARCH.md; plan step 3). Catalog and availability fixtures are
#: filtered to these sites, so tests never assert network-wide counts.
FIXTURE_SITES: tuple[str, ...] = (
    "AR-Bal",
    "BR-Sa1",
    "CA-Let",
    "DE-Tha",
    "GL-ZaF",
    "PR-xGU",
    "RU-Sam",
    "US-CRT",
    "US-Ha1",
    "US-Ha2",
    "US-Ha3",
    "US-Jo2",
    "US-Myb",
    "US-Seg",
    "US-xSR",
)


def canonical_key(method: str, url: httpx.URL) -> str:
    """``METHOD host/raw-path?sorted-query``; shared by the recorder and the router."""
    raw = url.raw_path.decode("ascii")
    path, _, query = raw.partition("?")
    params = sorted(parse_qsl(query, keep_blank_values=True))
    key = f"{method.upper()} {url.host}{path}"
    return f"{key}?{urlencode(params)}" if params else key


def load_manifest(path: Path = MANIFEST) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {e["key"]: e for e in entries}


@dataclass
class Reply:
    status: int = 200
    content: bytes = b""
    content_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, payload: Any, status: int = 200) -> Reply:
        return cls(status, json.dumps(payload).encode("utf-8"))


@dataclass
class Call:
    method: str
    url: str
    host: str
    path: str
    key: str
    headers: dict[str, str]
    body: bytes


Responder = Reply | Callable[[Call], Reply] | type[Exception]


def _private_values() -> tuple[str, ...]:
    from tests.helpers import PRIVATE_VALUES

    return PRIVATE_VALUES


class FixtureRouter:
    def __init__(self, manifest: dict[str, dict[str, Any]] | None = None) -> None:
        self.manifest = load_manifest() if manifest is None else manifest
        self.calls: list[Call] = []
        self.unexpected: list[str] = []
        self.extra: dict[str, Responder] = {}
        self._queued: list[Responder] = []

    # ---------------------------------------------------------------- configuration

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def add(self, key: str, responder: Responder) -> None:
        """Serve ``responder`` for ``canonical_key`` ``key`` (takes priority over fixtures)."""
        self.extra[key] = responder

    def inject(self, responder: Responder, times: int = 1) -> None:
        """Serve ``responder`` to the next ``times`` requests."""
        self._queued.extend([responder] * times)

    # ---------------------------------------------------------------- inspection

    def keys(self) -> list[str]:
        return [c.key for c in self.calls]

    def calls_to(self, path_prefix: str) -> list[Call]:
        return [c for c in self.calls if c.path.startswith(path_prefix)]

    # ---------------------------------------------------------------- handling

    def _fail(self, message: str) -> AssertionError:
        self.unexpected.append(message)
        return AssertionError(message)

    def handle(self, request: httpx.Request) -> httpx.Response:
        call = Call(
            method=request.method,
            url=str(request.url),
            host=request.url.host,
            path=request.url.path,
            key=canonical_key(request.method, request.url),
            headers={k.lower(): v for k, v in request.headers.items()},
            body=request.content,
        )
        self.calls.append(call)
        prefixes = ALLOWED.get(call.host)
        if prefixes is None or not any(call.path.startswith(p) for p in prefixes):
            raise self._fail(f"request outside the allow-list: {call.key}")
        if any(fragment in call.path for fragment in DENIED_FRAGMENTS):
            raise self._fail(f"request to a denied path: {call.key}")
        carried = "\n".join(
            (
                call.url,
                unquote_plus(call.url),
                json.dumps(call.headers),
                call.body.decode("utf-8", "replace"),
                unquote_plus(call.body.decode("utf-8", "replace")),
            )
        )
        if not (call.method == "POST" and call.path == DATA_DOWNLOAD_PATH):
            leaked = [v for v in _private_values() if v in carried]
            if leaked:
                raise self._fail(f"identity sent to {call.key}")
        if self._queued:
            return self._respond(self._queued.pop(0), call, request)
        if call.key in self.extra:
            return self._respond(self.extra[call.key], call, request)
        entry = self.manifest.get(call.key)
        if entry is None:
            if call.method != "GET":
                raise self._fail(f"{call.method} without a fixture: {call.key}")
            raise self._fail(f"unexpected upstream call: {call.key}")
        return self._finish(self._from_entry(entry))

    @staticmethod
    def _from_entry(entry: dict[str, Any]) -> Reply:
        content = (FIXTURES / entry["file"]).read_bytes() if entry.get("file") else b""
        return Reply(entry["status"], content, entry.get("contentType") or "")

    def _respond(self, responder: Responder, call: Call, request: httpx.Request) -> httpx.Response:
        if isinstance(responder, type) and issubclass(responder, Exception):
            raise responder("injected failure", request=request)  # type: ignore[call-arg]
        reply = responder(call) if callable(responder) else responder
        return self._finish(reply)

    @staticmethod
    def _finish(reply: Reply) -> httpx.Response:
        headers = {"content-type": reply.content_type} if reply.content_type else {}
        headers.update(reply.headers)
        return httpx.Response(reply.status, content=reply.content, headers=headers)


__all__ = [
    "FIXTURES",
    "FIXTURE_SITES",
    "Call",
    "FixtureRouter",
    "Reply",
    "canonical_key",
    "load_manifest",
]
