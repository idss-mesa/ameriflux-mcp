from __future__ import annotations

from ameriflux_mcp.ameriflux.identity import (
    CLIENT_TAG,
    identity_status,
    resolve_identity,
)
from ameriflux_mcp.config import load_config
from ameriflux_mcp.logging import registered_secrets
from tests.helpers import IDENTITY_ENV, PRIVATE_VALUES


def test_resolves_on_stdio_with_profiles() -> None:
    ident = resolve_identity(load_config(env=IDENTITY_ENV), transport="stdio")
    assert ident is not None
    assert ident.user_id == "fluxtester42" and ident.is_test is True
    default = ident.profile()
    assert default is not None and default.complete
    assert default.intended_use_label() == "Research - Other"
    assert default.tagged_description() == IDENTITY_ENV["AMERIFLUX_DESCRIPTION"] + CLIENT_TAG
    assert ident.fingerprint().startswith("id:") and len(ident.fingerprint()) == 15


def test_never_resolves_over_http() -> None:
    assert resolve_identity(load_config(env=IDENTITY_ENV), transport="http") is None


def test_incomplete_identity_does_not_resolve() -> None:
    env = {k: v for k, v in IDENTITY_ENV.items() if k != "AMERIFLUX_USER_EMAIL"}
    assert resolve_identity(load_config(env=env), transport="stdio") is None


def test_values_are_registered_for_redaction_even_when_incomplete() -> None:
    resolve_identity(load_config(env={"AMERIFLUX_USER_ID": "half-configured"}), transport="stdio")
    assert "half-configured" in registered_secrets()
    resolve_identity(load_config(env=IDENTITY_ENV), transport="stdio")
    assert set(PRIVATE_VALUES) <= registered_secrets()


def test_repr_reveals_nothing() -> None:
    ident = resolve_identity(load_config(env=IDENTITY_ENV), transport="stdio")
    text = repr(ident) + str(ident)
    for value in PRIVATE_VALUES:
        assert value not in text
    assert "default" in text


def test_status_reports_booleans_and_names_only() -> None:
    status = identity_status(load_config(env=IDENTITY_ENV), transport="stdio")
    assert status.available and status.reason == "ok" and status.configured
    assert status.profiles == ["default"] and status.complete_profiles == ["default"]
    assert status.is_test_set and status.is_test is True
    for value in PRIVATE_VALUES:
        assert value not in repr(status)


def test_status_over_http_reports_nothing_configured() -> None:
    status = identity_status(load_config(env=IDENTITY_ENV), transport="http")
    assert status.reason == "http" and not status.available
    assert not status.user_id_configured and not status.email_configured
    assert status.profiles == [] and not status.is_test_set


def test_status_incomplete() -> None:
    status = identity_status(load_config(env={"AMERIFLUX_USER_ID": "only-id"}), transport="stdio")
    assert status.reason == "incomplete" and not status.available
    assert status.user_id_configured and not status.email_configured
    assert not status.is_test_set
