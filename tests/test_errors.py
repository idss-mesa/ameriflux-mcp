from __future__ import annotations

from typing import Any

import pytest

from ameriflux_mcp.errors import (
    AmeriFluxApiError,
    InputRequired,
    ToolError,
    identity_required_error,
    map_api_error,
    redact,
)

PATH = "GET amfcdn.lbl.gov/api/v1/data_availability/AmeriFlux/BASE-BADM/CCBY4.0"


def err(status: int, detail: str = "x", **kw: Any) -> AmeriFluxApiError:
    return AmeriFluxApiError(status, detail, PATH, **kw)


@pytest.mark.parametrize(
    ("status", "detail", "code"),
    [
        (400, "Bad Request", "invalid_argument"),
        (404, '{"detail":{},"message":"Not Found"}', "not_found"),
        (410, "gone", "not_found"),
        (422, "Must be one of: TIER2, CCBY4.0.", "invalid_argument"),
        (405, "Method Not Allowed", "upstream_error"),
        (429, "slow down", "rate_limited"),
        (500, "boom", "upstream_error"),
        (502, "<html>", "upstream_error"),
        (521, "origin down", "upstream_unavailable"),
        (527, "railgun", "upstream_unavailable"),
        (418, "teapot", "upstream_error"),
    ],
)
def test_status_table(status: int, detail: str, code: str) -> None:
    assert map_api_error(err(status, detail)).code == code


def test_422_keeps_the_upstream_message() -> None:
    e = map_api_error(err(422, "Must be one of: TIER2, CCBY4.0."))
    assert "Must be one of: TIER2, CCBY4.0." in e.message and e.details["status"] == 422


def test_405_reports_drift() -> None:
    e = map_api_error(err(405, "Method Not Allowed"))
    assert e.details["drift"] == {"endpoint": PATH, "status": 405}


def test_drift_kind_lists_missing_keys() -> None:
    e = map_api_error(err(200, "shape changed", kind="drift", missing=["DOI_INFO"]))
    assert e.code == "upstream_error"
    assert e.details["drift"] == {"endpoint": PATH, "missing": ["DOI_INFO"]}


@pytest.mark.parametrize("status", [401, 403])
def test_forbidden_with_identity_points_at_the_guide(status: int) -> None:
    e = map_api_error(err(status, identity_sent=True))
    assert e.code == "upstream_forbidden" and e.details["guide"] == "ameriflux://guide/identity"
    assert "AMERIFLUX_USER_ID" in e.message
    plain = map_api_error(err(status))
    assert plain.code == "upstream_forbidden" and "guide" not in plain.details


def test_not_found_names_the_entity() -> None:
    e = map_api_error(err(404, "Not Found"), entity="site", identifier="XX-Zzz")
    assert e.code == "not_found" and e.details["identifier"] == "XX-Zzz"
    assert "site 'XX-Zzz'" in e.message


def test_service_name_and_rate_limit_details() -> None:
    e = map_api_error(err(429, retry_after_s=2.0, service="DataCite"))
    assert e.details["retryAfterSeconds"] == 2.0
    assert e.message.startswith("DataCite")


def test_transport_and_decode_kinds() -> None:
    transport = map_api_error(AmeriFluxApiError(0, "ConnectError", PATH, kind="transport"))
    assert transport.code == "upstream_unavailable" and "amf_ping" in (transport.hint or "")
    decoded = map_api_error(err(200, "not JSON", kind="decode", content_type="text/html"))
    assert decoded.code == "upstream_error" and decoded.details["contentType"] == "text/html"


def test_secrets_are_redacted_from_messages_and_endpoints() -> None:
    e = map_api_error(
        AmeriFluxApiError(
            400, "bad value someone@example.org here", PATH + "?u=someone@example.org"
        ),
        secrets=["someone@example.org"],
    )
    assert "someone@example.org" not in e.message and "someone@example.org" not in str(e.details)
    assert redact("a KEY b", ["KEY", ""]) == "a *** b"


def test_identity_required_error_details() -> None:
    e = identity_required_error(tool="amf_download_data", reason="is_test_unset", missing=["x"])
    assert e.code == "auth_required" and e.hint == "Read ameriflux://guide/identity."
    assert e.details == {
        "guide": "ameriflux://guide/identity",
        "tool": "amf_download_data",
        "reason": "is_test_unset",
        "missing": ["x"],
    }
    assert "site PIs" in e.message and "amfcdn.lbl.gov/create" in e.message


def test_payload_shape() -> None:
    assert ToolError("not_found", "m", details={"a": 1}, hint="h").to_payload() == {
        "error": {"code": "not_found", "message": "m", "details": {"a": 1}, "hint": "h"}
    }
    assert "hint" not in ToolError("invalid_argument", "m").to_payload()["error"]


def test_input_required_copies_its_inputs() -> None:
    schema = {"type": "object"}
    state = {"field": "x"}
    pending = InputRequired(key="k", message="pick", requested_schema=schema, state=state)
    schema["x"] = 1
    state["y"] = 2
    assert pending.requested_schema == {"type": "object"}
    assert pending.state == {"field": "x"}
