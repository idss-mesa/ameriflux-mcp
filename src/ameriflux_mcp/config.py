"""Configuration model and loader for ameriflux-mcp.

Precedence (highest wins): CLI flag > environment variable > YAML file > default.

Environment variables use the ``AMERIFLUX_MCP_`` prefix and ``__`` to descend
into nested sections at any depth: ``AMERIFLUX_MCP_UPSTREAM__RETRIES__MAX_ATTEMPTS``
sets ``config.upstream.retries.max_attempts``. List fields accept a
comma-separated string; an empty value counts as unset.

The download identity (DESIGN.md D12) also falls back to the plain names other
AmeriFlux tools use: ``AMERIFLUX_USER_ID``, ``AMERIFLUX_USER_EMAIL`` and
``AMERIFLUX_USER_NAME`` for ``identity.*``, and ``AMERIFLUX_INTENDED_USE`` /
``AMERIFLUX_DESCRIPTION`` for the ``default`` profile. The namespaced form wins
when both are set. Look-alike names (``AMERIFLUX_EMAIL``, ``AMF_USER_ID``, ...)
are not read; the loader warns when one is set. Identity never comes from a
flag.

The loader validates shape only; it never contacts AmeriFlux.
"""

from __future__ import annotations

import logging
import os
import re
import types as _pytypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

logger = logging.getLogger(__name__)

Transport = Literal["stdio", "http"]
LogLevel = Literal["debug", "info", "warning", "error", "critical"]
IntendedUse = Literal[
    "synthesis", "model", "remote_sensing", "other_research", "education", "other"
]

ENV_PREFIX = "AMERIFLUX_MCP_"
ENV_DELIM = "__"
#: Plain identity variables consulted when the namespaced ``identity.*`` field is unset.
IDENTITY_ENV_FALLBACKS: dict[str, str] = {
    "user_id": "AMERIFLUX_USER_ID",
    "user_email": "AMERIFLUX_USER_EMAIL",
    "user_name": "AMERIFLUX_USER_NAME",
}
#: Plain variables for the ``default`` profile.
PROFILE_ENV_FALLBACKS: dict[str, str] = {
    "intended_use": "AMERIFLUX_INTENDED_USE",
    "description": "AMERIFLUX_DESCRIPTION",
}
#: Plausible-looking variables that are *not* read (warned about when set).
IGNORED_IDENTITY_ENV: tuple[str, ...] = (
    "AMERIFLUX_EMAIL",
    "AMERIFLUX_USERNAME",
    "AMERIFLUX_USER",
    "AMERIFLUX_TOKEN",
    "AMERIFLUX_API_KEY",
    "AMF_USER_ID",
    "AMF_USER_EMAIL",
    "AMF_EMAIL",
)
#: Intended-use codes of AmeriFlux's download form (RESEARCH.md section 5).
INTENDED_USE_CODES: dict[str, IntendedUse] = {
    "1": "synthesis",
    "2": "model",
    "3": "remote_sensing",
    "4": "other_research",
    "5": "education",
    "6": "other",
}
#: The verbose category AmeriFlux receives for each key.
INTENDED_USE_LABELS: dict[IntendedUse, str] = {
    "synthesis": "Research - Multi-site synthesis",
    "model": "Research - Land model/Earth system model",
    "remote_sensing": "Research - Remote sensing",
    "other_research": "Research - Other",
    "education": "Education (Teacher or Student)",
    "other": "Other",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DESCRIPTION_MIN_CHARS = 20
DESCRIPTION_MAX_CHARS = 1000


class ConfigError(ValueError):
    """Invalid configuration. The message names fields and rules, never the values given
    (pydantic's own message would echo them, and identity values must not reach logs)."""


class _Section(BaseModel):
    # Unknown keys are warned about by the loader, not rejected: failing to
    # start over a stale key is worse than running with a documented default.
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class RetryConfig(_Section):
    """Retry policy for 429, 5xx and network failures (every API read is idempotent)."""

    max_attempts: int = Field(
        3, ge=1, le=10, description="Attempts per upstream call, including the first."
    )
    backoff_base_s: float = Field(
        0.5, ge=0, description="Base of the exponential backoff (0.5 * 2^n seconds)."
    )
    backoff_max_s: float = Field(8.0, ge=0, description="Cap on a single backoff sleep.")
    retry_after_default_s: float = Field(
        1.0, ge=0, description="Wait used on HTTP 429 when no Retry-After header is sent."
    )


class UpstreamConfig(_Section):
    """The AmeriFlux API (amfcdn.lbl.gov) and politeness settings (DESIGN.md D21)."""

    api_base_url: str = Field(
        "https://amfcdn.lbl.gov/api",
        description="AmeriFlux API base URL (v1 and v2 paths are appended per endpoint).",
    )
    user_agent_suffix: str | None = Field(
        None, description="Text appended to the User-Agent header."
    )
    connect_timeout_s: float = Field(10.0, gt=0, description="TCP/TLS connect timeout.")
    read_timeout_s: float = Field(60.0, gt=0, description="Default read timeout.")
    download_read_timeout_s: float = Field(
        300.0, gt=0, description="Read timeout for data file downloads."
    )
    requests_per_second: float = Field(
        2.0, gt=0, le=10, description="Rate limit towards the AmeriFlux API (local policy)."
    )
    max_concurrency: int = Field(
        4, ge=1, le=16, description="Maximum simultaneous upstream requests."
    )
    max_response_bytes: int = Field(
        20 * 1024 * 1024,
        ge=1024,
        description="Largest upstream response body read into memory (the site catalog is 1.7 MB).",
    )
    retries: RetryConfig = Field(default_factory=RetryConfig)


class ProfileConfig(_Section):
    """One named download profile: the intended use and description sent to site PIs."""

    intended_use: IntendedUse | None = Field(
        None,
        description="Intended-use category: 1-6 or synthesis, model, remote_sensing, "
        "other_research, education, other.",
    )
    description: str | None = Field(
        None,
        description="How you will use the data, in your own words (20-1000 characters); "
        "' [ameriflux-mcp]' is appended when sent.",
    )

    @field_validator("intended_use", mode="before")
    @classmethod
    def _use_code(cls, value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if isinstance(value, str):
            value = value.strip().lower()
            return INTENDED_USE_CODES.get(value, value) or None
        return value

    @field_validator("description", mode="after")
    @classmethod
    def _description_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            return None
        if not DESCRIPTION_MIN_CHARS <= len(value) <= DESCRIPTION_MAX_CHARS:
            raise ValueError(
                f"description must be {DESCRIPTION_MIN_CHARS}-{DESCRIPTION_MAX_CHARS} characters "
                f"(got {len(value)})"
            )
        return value


class IdentityConfig(_Section):
    """The download identity (stdio only; sent to site PIs on a confirmed download)."""

    user_id: SecretStr | None = Field(
        None, description="AmeriFlux username sent with downloads (or AMERIFLUX_USER_ID)."
    )
    user_email: SecretStr | None = Field(
        None,
        description="Email registered with AmeriFlux, sent with downloads (or AMERIFLUX_USER_EMAIL).",
    )
    user_name: SecretStr | None = Field(
        None, description="Optional name sent with downloads (or AMERIFLUX_USER_NAME)."
    )
    profiles: dict[str, ProfileConfig] = Field(
        default_factory=dict,
        description="Named profiles of intended use and description; AMERIFLUX_INTENDED_USE and "
        "AMERIFLUX_DESCRIPTION fill 'default'.",
    )
    is_test: bool | None = Field(
        None, description="Send downloads as test requests. Must be set before any download."
    )

    @field_validator("user_email", mode="after")
    @classmethod
    def _email_shape(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        text = value.get_secret_value().strip()
        if not text:
            return None
        if not EMAIL_RE.match(text):
            raise ValueError("user_email is not an email address")  # the value is not echoed
        return SecretStr(text)

    @field_validator("user_id", "user_name", mode="after")
    @classmethod
    def _strip(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        text = value.get_secret_value().strip()
        return SecretStr(text) if text else None


class CacheTTLs(_Section):
    """Time-to-live, in seconds, per cache family (DESIGN.md D22)."""

    catalog: int = Field(21600, ge=0, description="Site catalog (6 h).")
    availability: int = Field(21600, ge=0, description="Availability lists (6 h).")
    fluxnet2015: int = Field(
        2592000, ge=0, description="Frozen FLUXNET2015 and FLUXNET-CH4 lists (30 d)."
    )
    variables: int = Field(86400, ge=0, description="FP Standard variable list (24 h).")
    citations: int = Field(86400, ge=0, description="DOI citations (24 h, memory only).")
    dictionaries: int = Field(2592000, ge=0, description="FLUXNET variable dictionaries (30 d).")
    heights: int = Field(86400, ge=0, description="Measurement heights (24 h).")
    coverage: int = Field(604800, ge=0, description="Variable coverage snapshots (7 d).")


class CacheConfig(_Section):
    """Response cache: in memory, plus a disk layer on stdio."""

    enabled: bool = Field(True, description="Cache AmeriFlux API responses.")
    max_entries: int = Field(1024, ge=1, description="Overall in-memory entry cap.")
    stale_if_error_s: int = Field(
        604800, ge=0, description="How long an expired entry may be served when a refresh fails."
    )
    disk_dir: Path | None = Field(
        None,
        description="On-disk cache (personal fields removed). Unset: ~/.cache/ameriflux-mcp on "
        "stdio, none over http.",
    )
    ttl_s: CacheTTLs = Field(default_factory=CacheTTLs)

    @field_validator("disk_dir", mode="after")
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return value.expanduser().resolve() if value is not None else None


class LimitsConfig(_Section):
    """Result-size and request-shape limits (DESIGN.md D23)."""

    default_limit: int = Field(
        25, ge=1, description="Default page size where a tool does not set its own."
    )
    max_limit: int = Field(200, ge=1, description="Largest page size any tool accepts.")
    max_result_bytes: int = Field(
        50_000,
        ge=1000,
        description="Tool results are trimmed (with page.truncated) to fit this many bytes of compact JSON.",
    )
    hard_max_result_bytes: int = Field(
        200_000,
        ge=1000,
        description="A result still larger than this after trimming fails with result_too_large.",
    )
    max_resource_bytes: int = Field(
        1024 * 1024,
        ge=1024,
        description="Largest resource read returned; larger ones fail with result_too_large.",
    )
    preview_max_rows: int = Field(500, ge=1, description="Most rows amf_preview_data returns.")
    preview_scan_max_bytes: int = Field(
        256 * 1024 * 1024, ge=1024, description="Most bytes a preview scans (256 MiB)."
    )
    preview_time_budget_s: float = Field(
        20.0, gt=0, description="Wall-clock budget for one preview scan."
    )
    zip_member_max_bytes: int = Field(
        1024**3, ge=1024, description="Largest zip member read (uncompressed)."
    )
    tools_list_max_bytes: int = Field(
        80_000,
        ge=1000,
        description="Conformance bound on the serialized tools/list result (59,945 B with the 11 "
        "stdio tools of step 6; reset to measured x1.25 in step 8, as in neon-mcp).",
    )


class DownloadsConfig(_Section):
    """Local downloads (stdio only, DESIGN.md D18)."""

    enabled: bool | None = Field(
        None,
        description="Offer the download tool. Unset: true on stdio; never available over http.",
    )
    directory: Path = Field(
        Path("~/ameriflux-downloads"),
        validate_default=True,
        description="Directory every download is confined to (created on first use).",
    )
    max_files_per_call: int = Field(50, ge=1, description="Most files one download call transfers.")
    max_bytes_per_call: int = Field(
        2 * 1024**3, ge=1, description="Most bytes one download call transfers (2 GiB)."
    )
    max_file_bytes: int = Field(1024**3, ge=1, description="Largest single file accepted (1 GiB).")

    @field_validator("directory", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class LocalConfig(_Section):
    """Where the local file tools may read (stdio only)."""

    roots: list[Path] = Field(
        default_factory=list,
        description="Extra directories the local file tools may read (the download directory "
        "is always included), e.g. FLUXNET2015 zips from fluxnet.org.",
    )

    @field_validator("roots", mode="after")
    @classmethod
    def _expand(cls, value: list[Path]) -> list[Path]:
        return [p.expanduser().resolve() for p in value]


class PrivacyConfig(_Section):
    """Personal data in results (DESIGN.md D19)."""

    allow_contact_emails: bool = Field(
        False,
        description="Allow team and contributor emails in results when a call asks for contacts.",
    )


class ServerConfig(_Section):
    """Transport and HTTP binding. There are no identity headers (DESIGN.md D25)."""

    transport: Transport = Field(
        "stdio", description="stdio (local clients) or http (stateless Streamable HTTP at /mcp)."
    )
    bind_address: str = Field("127.0.0.1", description="HTTP bind address.")
    bind_port: int = Field(8080, ge=1, le=65535, description="HTTP bind port.")
    public_base_url: str | None = Field(
        None,
        description="Public URL of a hosted deployment; its host/origin join the allow-lists.",
    )
    allowed_hosts: list[str] = Field(
        default_factory=list, description="Host header allow-list (DNS-rebinding protection)."
    )
    allowed_origins: list[str] = Field(
        default_factory=list, description="Origin header allow-list (DNS-rebinding protection)."
    )
    dns_rebinding_protection: bool | None = Field(
        None,
        description="Force DNS-rebinding protection on/off. "
        "Unset: SDK default (on for loopback binds or when allow-lists are set).",
    )
    json_response: bool = Field(
        False, description="Answer POST /mcp with application/json instead of a single SSE frame."
    )
    max_request_body_size: int = Field(
        1024 * 1024, ge=1024, description="Largest accepted request body in bytes."
    )
    tools_list_ttl_ms: int = Field(300_000, ge=0, description="ttlMs advertised on tools/list.")
    log_level: LogLevel = Field("info", description="Log verbosity.")
    instructions_extra: str | None = Field(
        None, description="Text appended to the server instructions."
    )


class Config(BaseModel):
    """Root configuration object."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    downloads: DownloadsConfig = Field(default_factory=DownloadsConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    def model_dump_redacted(self) -> dict[str, Any]:
        """JSON-safe dump with identity values replaced by ``***`` (for --print-config)."""
        data = self.model_dump(mode="json")
        for name in ("user_id", "user_email", "user_name"):
            data["identity"][name] = "***" if getattr(self.identity, name) is not None else None
        return data

    def effective_downloads_enabled(self, transport: str) -> bool:
        """Downloads exist only on stdio, and only unless explicitly disabled."""
        return transport == "stdio" and self.downloads.enabled is not False

    def effective_disk_cache(self, transport: str) -> Path | None:
        """The disk cache directory: configured, else the default on stdio, else none."""
        if self.cache.disk_dir is not None:
            return self.cache.disk_dir
        if transport == "stdio" and self.cache.enabled:
            return Path("~/.cache/ameriflux-mcp").expanduser().resolve()
        return None

    def local_roots(self) -> list[Path]:
        """Directories the local file tools may read: the download directory first."""
        roots = [self.downloads.directory]
        roots.extend(r for r in self.local.roots if r not in roots)
        return roots


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _coerce_env_value(raw: str) -> Any:
    """Env values stay strings (pydantic coerces them); ``null`` / ``none`` become ``None``."""
    if raw.strip().lower() in {"null", "none"}:
        return None
    return raw


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a YAML mapping at the top level.")
    return data


def _load_env(env: Mapping[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in env.items():
        if not key.startswith(ENV_PREFIX):
            continue
        if not raw.strip():
            continue  # VAR= (as docker compose passes an unset ${VAR:-}) means "not set"
        parts = [p.lower() for p in key[len(ENV_PREFIX) :].split(ENV_DELIM) if p]
        if not parts:
            continue
        cursor: dict[str, Any] = out
        conflict = False
        for part in parts[:-1]:
            nxt = cursor.setdefault(part, {})
            if not isinstance(nxt, dict):
                conflict = True
                break
            cursor = nxt
        if not conflict:
            cursor[parts[-1]] = _coerce_env_value(raw)
    return out


def _unwrap_optional(annotation: Any) -> list[Any]:
    origin = get_origin(annotation)
    if origin in (Union, _pytypes.UnionType):
        return [a for a in get_args(annotation) if a is not type(None)]
    return [annotation]


def _is_list(annotation: Any) -> bool:
    return any(get_origin(a) is list for a in _unwrap_optional(annotation))


def _submodel(annotation: Any) -> type[BaseModel] | None:
    for a in _unwrap_optional(annotation):
        if isinstance(a, type) and issubclass(a, BaseModel):
            return a
    return None


def _dict_values_model(annotation: Any) -> type[BaseModel] | None:
    """The value model of a ``dict[str, Model]`` field (identity.profiles)."""
    for a in _unwrap_optional(annotation):
        if get_origin(a) is dict:
            args = get_args(a)
            if len(args) == 2 and isinstance(args[1], type) and issubclass(args[1], BaseModel):
                return args[1]
    return None


def _drop_empty_sections(data: dict[str, Any], model: type[BaseModel]) -> None:
    """A YAML section left with only comments (``cache:``) loads as null: treat it as absent."""
    for name, field in model.model_fields.items():
        if name not in data:
            continue
        sub = _submodel(field.annotation)
        if sub is None:
            continue
        if data[name] is None:
            del data[name]
        elif isinstance(data[name], dict):
            _drop_empty_sections(data[name], sub)


def _normalize_lists(data: dict[str, Any], model: type[BaseModel]) -> None:
    """Split comma-separated strings destined for list fields (env convenience)."""
    for name, field in model.model_fields.items():
        if name not in data:
            continue
        value = data[name]
        if isinstance(value, str) and _is_list(field.annotation):
            data[name] = [p.strip() for p in value.split(",") if p.strip()]
        elif isinstance(value, dict):
            sub = _submodel(field.annotation)
            if sub is not None:
                _normalize_lists(value, sub)


def _warn_unknown_keys(
    layer: Mapping[str, Any], model: type[BaseModel] = Config, *, source: str, prefix: str = ""
) -> list[str]:
    """Log (and return) dotted keys no model field consumes."""
    unknown: list[str] = []
    for key, value in layer.items():
        dotted = f"{prefix}{key}"
        field = model.model_fields.get(key)
        if field is None:
            unknown.append(dotted)
            logger.warning(
                "config: unknown key %r from %s ignored (check spelling)", dotted, source
            )
            continue
        sub = _submodel(field.annotation)
        if sub is not None and isinstance(value, dict):
            unknown.extend(_warn_unknown_keys(value, sub, source=source, prefix=f"{dotted}."))
            continue
        values_model = _dict_values_model(field.annotation)
        if values_model is not None and isinstance(value, dict):
            for entry, sub_value in value.items():
                if isinstance(sub_value, dict):
                    unknown.extend(
                        _warn_unknown_keys(
                            sub_value, values_model, source=source, prefix=f"{dotted}.{entry}."
                        )
                    )
    return unknown


_FLAG_PATHS: dict[str, tuple[str, str]] = {
    "transport": ("server", "transport"),
    "bind_address": ("server", "bind_address"),
    "bind_port": ("server", "bind_port"),
    "log_level": ("server", "log_level"),
    "download_dir": ("downloads", "directory"),
    "downloads_enabled": ("downloads", "enabled"),
}


def _flags_to_layer(flag_overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    layer: dict[str, Any] = {}
    for key, value in (flag_overrides or {}).items():
        if value is None:
            continue
        if key not in _FLAG_PATHS:
            raise KeyError(f"unknown flag override {key!r}")
        section, field = _FLAG_PATHS[key]
        layer.setdefault(section, {})[field] = value
    return layer


def _apply_identity_fallbacks(merged: dict[str, Any], env: Mapping[str, str]) -> None:
    """Fill unset identity fields from the plain AMERIFLUX_* names; warn on look-alikes."""
    identity = merged.get("identity")
    if identity is not None and not isinstance(identity, dict):
        return
    identity = merged.setdefault("identity", {})
    for field, name in IDENTITY_ENV_FALLBACKS.items():
        value = env.get(name, "").strip()
        if value and not identity.get(field):
            identity[field] = value
    profiles = identity.get("profiles")
    if profiles is None or isinstance(profiles, dict):
        profiles = identity.setdefault("profiles", {})
        default = profiles.get("default")
        if default is None or isinstance(default, dict):
            default = profiles.setdefault("default", {})
            for field, name in PROFILE_ENV_FALLBACKS.items():
                value = env.get(name, "").strip()
                if value and not default.get(field):
                    default[field] = value
            if not default:
                profiles.pop("default")
        if not profiles:
            identity.pop("profiles")
    if not identity:
        merged.pop("identity")
    for name in IGNORED_IDENTITY_ENV:
        if env.get(name, "").strip():
            logger.warning(
                "%s is set but ameriflux-mcp does not read it; see ameriflux://guide/identity "
                "for the names it uses (AMERIFLUX_USER_ID, AMERIFLUX_USER_EMAIL, ...)",
                name,
            )


def load_config(
    path: Path | None = None,
    *,
    flag_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> Config:
    """Load configuration with precedence flag > env > YAML > defaults."""
    source_env = os.environ if env is None else env
    yaml_layer = _load_yaml(path) if path is not None else {}
    env_layer = _load_env(source_env)
    flag_layer = _flags_to_layer(flag_overrides)

    _warn_unknown_keys(yaml_layer, source="config file")
    _warn_unknown_keys(env_layer, source="environment")

    merged = _deep_merge(_deep_merge(yaml_layer, env_layer), flag_layer)
    _drop_empty_sections(merged, Config)
    _apply_identity_fallbacks(merged, source_env)
    _normalize_lists(merged, Config)
    try:
        return Config.model_validate(merged)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in err.get('loc', ())) or 'config'}: {err.get('msg')}"
            for err in exc.errors(include_input=False, include_url=False, include_context=False)
        ]
        raise ConfigError("invalid configuration:\n  " + "\n  ".join(problems)) from None


# ---------------------------------------------------------------------------
# Process-wide active config
# ---------------------------------------------------------------------------

_active_config: Config | None = None


def set_active_config(config: Config | None) -> None:
    """Record (or clear) the resolved config; called by the CLI entry point."""
    global _active_config
    _active_config = config


def get_active_config() -> Config:
    """The config set by the entry point, or env + defaults when none was set."""
    return _active_config if _active_config is not None else load_config()
