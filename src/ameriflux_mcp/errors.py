"""Structured error types for ameriflux-mcp.

Tool handlers raise :class:`ToolError` for every user-facing failure; the
server boundary turns it into an ``isError`` tool result whose
``structuredContent`` is ``{"error": {"code", "message", "details", "hint"}}``.
Python tracebacks never reach the wire.

:class:`AmeriFluxApiError` is what the HTTP client raises for a failed upstream
call; :func:`map_api_error` translates it into a :class:`ToolError` (DESIGN.md
D24: edi-mcp's 16 codes, specifics in ``details.reason``). The AmeriFlux API is
anonymous, so a 401/403 is never "missing credentials": only the download
request carries an identity, and AmeriFlux refusing it is ``upstream_forbidden``,
never a silent downgrade.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

ErrorCode = Literal[
    "invalid_argument",
    "not_found",
    "ambiguous_input",
    "auth_required",
    "upstream_forbidden",
    "rate_limited",
    "upstream_error",
    "upstream_unavailable",
    "feature_unavailable",
    "not_available_in_http_mode",
    "download_limit_exceeded",
    "download_denied",
    "checksum_mismatch",
    "result_too_large",
    "unknown_tool",
    "internal_error",
]

#: Resource every ``auth_required`` error points at.
IDENTITY_GUIDE = "ameriflux://guide/identity"
#: Where AmeriFlux and FLUXNET users create the shared account.
ACCOUNT_PAGE_URL = "https://amfcdn.lbl.gov/create"

IDENTITY_REQUIRED_MESSAGE = (
    "Downloading from AmeriFlux needs your download identity: AmeriFlux sends your user ID, "
    "email, intended use and description to the site PIs with every download. Set "
    "AMERIFLUX_USER_ID, AMERIFLUX_USER_EMAIL, AMERIFLUX_INTENDED_USE, AMERIFLUX_DESCRIPTION and "
    "AMERIFLUX_MCP_IDENTITY__IS_TEST in the server's environment (stdio only; create an account "
    f"at {ACCOUNT_PAGE_URL}). Site search, availability, variables and citations need no identity."
)


class ToolError(Exception):
    """A structured, user-facing failure raised from a tool handler.

    ``code`` is a stable machine-readable :data:`ErrorCode`; ``message`` is
    safe to show a user and never contains identity values; ``details`` is
    JSON-serializable context; ``hint`` is an optional one-line remedy.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}
        self.hint = hint

    def to_payload(self) -> dict[str, Any]:
        """Return the ``{"error": {...}}`` structure sent as ``structuredContent``."""
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.hint:
            error["hint"] = self.hint
        return {"error": error}

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"ToolError(code={self.code!r}, message={self.message!r})"


class InputRequired(Exception):
    """Raised by a handler that needs one more round trip with the user (MRTR).

    The server boundary turns it into an ``InputRequiredResult`` carrying an
    ``elicitation/create`` form. ``state`` travels out to the client and back
    as ``requestState``; it must hold only the question being asked — never an
    identity value, a filesystem path or an authorization decision — because the
    client controls it by the time it returns. (No ameriflux-mcp tool elicits in
    v0.1; downloads use plan-then-confirm instead, DESIGN.md D13.)
    """

    def __init__(
        self,
        *,
        key: str,
        message: str,
        requested_schema: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> None:
        super().__init__(message)
        self.key = key
        self.message = message
        self.requested_schema: dict[str, Any] = dict(requested_schema)
        self.state: dict[str, Any] = dict(state)


class AmeriFluxApiError(Exception):
    """A failed upstream call (the AmeriFlux API, its file server, or DataCite).

    ``kind`` distinguishes an HTTP error status (``http``), a network failure
    or timeout after retries (``transport``, ``status == 0``), a response that
    could not be parsed (``decode``) and a response whose shape no longer matches
    what ameriflux-mcp expects (``drift``, DESIGN.md D8). ``path`` never carries
    identity values.
    """

    def __init__(
        self,
        status: int,
        detail: str,
        path: str,
        *,
        retry_after_s: float | None = None,
        headers: Mapping[str, str] | None = None,
        kind: Literal["http", "transport", "decode", "drift"] = "http",
        content_type: str | None = None,
        identity_sent: bool = False,
        service: str = "The AmeriFlux API",
        missing: Iterable[str] = (),
    ) -> None:
        super().__init__(f"{status} {path}: {detail}")
        self.status = status
        self.detail = detail
        self.path = path
        self.retry_after_s = retry_after_s
        self.headers: dict[str, str] = dict(headers or {})
        self.kind = kind
        self.content_type = content_type
        #: Whether the failed request carried the user's download identity.
        self.identity_sent = identity_sent
        #: Human name of the upstream service, used in messages.
        self.service = service
        #: Required keys absent from a drifted response.
        self.missing: list[str] = list(missing)


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each non-empty secret in ``text`` with ``***``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def identity_required_error(
    *, tool: str | None = None, reason: str | None = None, missing: Iterable[str] = ()
) -> ToolError:
    """The ``auth_required`` error for a download without a usable identity."""
    details: dict[str, Any] = {"guide": IDENTITY_GUIDE}
    if tool:
        details["tool"] = tool
    if reason:
        details["reason"] = reason
    missing = list(missing)
    if missing:
        details["missing"] = missing
    return ToolError(
        "auth_required",
        IDENTITY_REQUIRED_MESSAGE,
        details=details,
        hint=f"Read {IDENTITY_GUIDE}.",
    )


def map_api_error(
    exc: AmeriFluxApiError,
    *,
    identity_sent: bool | None = None,
    entity: str | None = None,
    identifier: str | None = None,
    secrets: Iterable[str] = (),
) -> ToolError:
    """Translate an upstream failure into a :class:`ToolError` (DESIGN.md D24)."""
    secrets = tuple(secrets)
    if identity_sent is None:
        identity_sent = exc.identity_sent
    detail = redact(exc.detail or "", secrets)[:500]
    endpoint = redact(exc.path, secrets)
    service = exc.service

    if exc.kind == "transport":
        return ToolError(
            "upstream_unavailable",
            f"{service} could not be reached (network error or timeout).",
            details={"reason": detail, "endpoint": endpoint},
            hint="Retry in a moment; call amf_ping with check_api=true to check connectivity.",
        )
    if exc.kind == "decode":
        return ToolError(
            "upstream_error",
            f"{service} returned a response that could not be parsed.",
            details={"status": exc.status, "contentType": exc.content_type, "endpoint": endpoint},
        )
    if exc.kind == "drift":
        return ToolError(
            "upstream_error",
            f"{service} answered with a shape ameriflux-mcp does not recognize; the undocumented "
            "API may have changed.",
            details={"drift": {"endpoint": endpoint, "missing": exc.missing}, "upstream": detail},
            hint="Report it at https://github.com/idss-mesa/ameriflux-mcp/issues.",
        )

    status = exc.status
    if status in (401, 403):
        if identity_sent:
            return ToolError(
                "upstream_forbidden",
                f"{service} refused the download request (HTTP {status}). Check that "
                "AMERIFLUX_USER_ID and AMERIFLUX_USER_EMAIL match your AmeriFlux account and that "
                "the data policy you accepted applies to these sites.",
                details={"guide": IDENTITY_GUIDE, "endpoint": endpoint, "status": status},
                hint=f"Read {IDENTITY_GUIDE}.",
            )
        return ToolError(
            "upstream_forbidden",
            f"{service} refused the request (HTTP {status}).",
            details={"endpoint": endpoint, "status": status, "upstream": detail},
        )
    if status in (404, 410):
        details: dict[str, Any] = {"endpoint": endpoint}
        if entity:
            details["entity"] = entity
        if identifier:
            details["identifier"] = identifier
        what = f"{entity} {identifier!r}" if entity and identifier else "The requested item"
        return ToolError(
            "not_found", f"{what} was not found. {service} said: {detail}", details=details
        )
    if status in (400, 422):
        return ToolError(
            "invalid_argument",
            f"{service} rejected the request: {detail}",
            details={"endpoint": endpoint, "status": status},
        )
    if status == 405:
        return ToolError(
            "upstream_error",
            f"{service} no longer accepts this method on {endpoint}; the undocumented API may "
            "have changed.",
            details={"drift": {"endpoint": endpoint, "status": status}},
        )
    if status == 429:
        return ToolError(
            "rate_limited",
            f"{service} rate limit was exceeded; wait before retrying.",
            details={"retryAfterSeconds": exc.retry_after_s, "endpoint": endpoint},
        )
    if 520 <= status <= 527:
        # Cloudflare origin errors: the API is behind Cloudflare and these mean "unreachable".
        return ToolError(
            "upstream_unavailable",
            f"{service} is unreachable behind its CDN (HTTP {status}).",
            details={"status": status, "endpoint": endpoint},
            hint="Retry in a moment.",
        )
    if status >= 500:
        return ToolError(
            "upstream_error",
            f"{service} failed with HTTP {status}.",
            details={"status": status, "endpoint": endpoint, "body": detail[:200]},
        )
    return ToolError(
        "upstream_error",
        f"{service} answered HTTP {status}: {detail}",
        details={"status": status, "endpoint": endpoint},
    )
