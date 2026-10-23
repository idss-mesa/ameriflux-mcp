"""A stand-in for the AmeriFlux API in hermetic tests (build step 2).

Every server built by the test fixtures talks to an :class:`UpstreamStub` through
``httpx.MockTransport``. It answers ``GET /api/v1/fp_var`` with a small canned list,
records every call, can inject failures, and fails the test on any request it has no
answer for (including any method other than GET). Build step 3 replaces it with the
recorded-fixture router.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

FP_VAR: list[dict[str, Any]] = [
    {
        "Name": "FC",
        "Type": "GASES",
        "Units": "µmolCO2 m-2 s-1",
        "Description": "Carbon Dioxide (CO2) turbulent flux (no storage correction)",
        "Sequence": 150,
        "ModelType": "SAGA",
        "HeightDirection": "pos",
    },
    {
        "Name": "TA",
        "Type": "MET_ATM",
        "Units": "deg C",
        "Description": "Air temperature",
        "Sequence": 400,
        "ModelType": "TA",
        "HeightDirection": "pos",
    },
]


@dataclass
class Call:
    method: str
    host: str
    path: str
    headers: dict[str, str]


@dataclass
class UpstreamStub:
    calls: list[Call] = field(default_factory=list)
    #: Queued failures: an exception class to raise, or an int status to answer.
    failures: list[Any] = field(default_factory=list)
    #: Overrides for a path, e.g. {"/api/v1/fp_var": (200, {"unexpected": True})}.
    answers: dict[str, tuple[int, Any]] = field(default_factory=dict)

    def inject(self, failure: Any, times: int = 1) -> None:
        self.failures.extend([failure] * times)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            Call(request.method, request.url.host, request.url.path, dict(request.headers))
        )
        if request.method != "GET":
            raise AssertionError(f"unexpected {request.method} {request.url}")
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, int):
                return httpx.Response(failure, text="stub failure")
            raise failure("stub", request=request)
        if request.url.path in self.answers:
            status, body = self.answers[request.url.path]
            return httpx.Response(status, json=body)
        if request.url.host == "amfcdn.lbl.gov" and request.url.path == "/api/v1/fp_var":
            return httpx.Response(200, json=FP_VAR)
        raise AssertionError(f"no stub answer for {request.method} {request.url}")

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
