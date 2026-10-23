"""The download identity: resolution per call, redaction and status reporting.

AmeriFlux has no API keys. A download request carries the user's AmeriFlux
user ID, email, intended use and description, and AmeriFlux forwards them to
the site PIs (DESIGN.md D11-D13). ameriflux-mcp therefore:

* reads the identity from configuration only (env or YAML), never from tool
  arguments, flags or HTTP headers;
* resolves it only on stdio: a hosted (HTTP) server never acts for a user
  (D25);
* registers every value with the log redactor (pinned) and never prints it:
  :class:`Identity` has no ``repr`` of its values, and :meth:`Identity.status`
  reports booleans and profile names only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from ameriflux_mcp.config import INTENDED_USE_LABELS, IntendedUse
from ameriflux_mcp.logging import register_secret

if TYPE_CHECKING:
    from ameriflux_mcp.config import Config

#: Appended to every description sent upstream (DESIGN.md D12).
CLIENT_TAG = " [ameriflux-mcp]"
DEFAULT_PROFILE = "default"


@dataclass(frozen=True)
class Profile:
    """One named profile: what the PIs are told about the intended use."""

    name: str
    intended_use: IntendedUse | None
    description: str | None

    @property
    def complete(self) -> bool:
        return self.intended_use is not None and self.description is not None

    def intended_use_label(self) -> str | None:
        """The verbose category AmeriFlux's form uses, e.g. 'Research - Other'."""
        return INTENDED_USE_LABELS[self.intended_use] if self.intended_use else None

    def tagged_description(self) -> str | None:
        return self.description + CLIENT_TAG if self.description else None


@dataclass(frozen=True, repr=False)
class Identity:
    """A configured download identity. ``repr``/``str`` never reveal the values."""

    user_id: str = field(repr=False)
    user_email: str = field(repr=False)
    user_name: str | None = field(default=None, repr=False)
    is_test: bool | None = None
    profiles: Mapping[str, Profile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.user_id, self.user_email, self.user_name):
            register_secret(value, pinned=True)

    def fingerprint(self) -> str:
        """Stable non-reversible label (for logs that must tell identities apart)."""
        digest = hashlib.sha256(f"{self.user_id}\0{self.user_email}".encode()).hexdigest()
        return "id:" + digest[:12]

    def profile(self, name: str = DEFAULT_PROFILE) -> Profile | None:
        return self.profiles.get(name)

    def __repr__(self) -> str:
        return f"Identity(<redacted>, profiles={sorted(self.profiles)!r}, is_test={self.is_test!r})"

    __str__ = __repr__


@dataclass(frozen=True)
class IdentityStatus:
    """What is configured, as booleans and names only (amf_ping, --check)."""

    user_id_configured: bool
    email_configured: bool
    name_configured: bool
    profiles: list[str]
    complete_profiles: list[str]
    is_test_set: bool
    is_test: bool | None
    available: bool
    reason: Literal["ok", "http", "incomplete"]

    @property
    def configured(self) -> bool:
        """User ID and email are both set (whether or not this transport may use them)."""
        return self.user_id_configured and self.email_configured


def _profiles(config: Config) -> dict[str, Profile]:
    return {
        name: Profile(name=name, intended_use=p.intended_use, description=p.description)
        for name, p in sorted(config.identity.profiles.items())
    }


def resolve_identity(config: Config, *, transport: Literal["stdio", "http"]) -> Identity | None:
    """The identity this call may act with: stdio only, and only with user ID and email."""
    if transport != "stdio":
        return None
    cfg = config.identity
    if cfg.user_id is None or cfg.user_email is None:
        # Register what is there anyway, so a half-configured identity still never logs.
        for secret in (cfg.user_id, cfg.user_email, cfg.user_name):
            if secret is not None:
                register_secret(secret.get_secret_value(), pinned=True)
        return None
    return Identity(
        user_id=cfg.user_id.get_secret_value(),
        user_email=cfg.user_email.get_secret_value(),
        user_name=cfg.user_name.get_secret_value() if cfg.user_name is not None else None,
        is_test=cfg.is_test,
        profiles=_profiles(config),
    )


def identity_status(config: Config, *, transport: Literal["stdio", "http"]) -> IdentityStatus:
    """Report the configured identity without revealing it.

    Over HTTP nothing is reported as configured: a hosted server never acts for a user,
    and callers have no business learning what its operator configured.
    """
    if transport != "stdio":
        return IdentityStatus(
            user_id_configured=False,
            email_configured=False,
            name_configured=False,
            profiles=[],
            complete_profiles=[],
            is_test_set=False,
            is_test=None,
            available=False,
            reason="http",
        )
    cfg = config.identity
    profiles = _profiles(config)
    configured = cfg.user_id is not None and cfg.user_email is not None
    reason: Literal["ok", "http", "incomplete"] = "ok" if configured else "incomplete"
    return IdentityStatus(
        user_id_configured=cfg.user_id is not None,
        email_configured=cfg.user_email is not None,
        name_configured=cfg.user_name is not None,
        profiles=sorted(profiles),
        complete_profiles=sorted(n for n, p in profiles.items() if p.complete),
        is_test_set=cfg.is_test is not None,
        is_test=cfg.is_test,
        available=reason == "ok",
        reason=reason,
    )


__all__ = [
    "CLIENT_TAG",
    "DEFAULT_PROFILE",
    "Identity",
    "IdentityStatus",
    "Profile",
    "identity_status",
    "resolve_identity",
]
