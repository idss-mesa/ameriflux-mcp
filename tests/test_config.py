from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ameriflux_mcp.config import (
    Config,
    ConfigError,
    get_active_config,
    load_config,
    set_active_config,
)
from tests.helpers import IDENTITY_ENV, PRIVATE_VALUES


def test_defaults_and_effective_values() -> None:
    cfg = load_config(env={})
    assert cfg.server.transport == "stdio"
    assert cfg.upstream.api_base_url == "https://amfcdn.lbl.gov/api"
    assert cfg.upstream.requests_per_second == 2.0 and cfg.upstream.max_concurrency == 4
    assert cfg.identity.user_id is None and cfg.identity.profiles == {}
    assert cfg.identity.is_test is None
    assert cfg.privacy.allow_contact_emails is False
    assert cfg.limits.max_result_bytes == 50_000 and cfg.limits.preview_max_rows == 500
    assert cfg.limits.preview_scan_max_bytes == 256 * 1024 * 1024
    # Off until AmeriFlux confirms third-party use (D18); never over HTTP.
    assert cfg.downloads.enabled is False
    assert not cfg.effective_downloads_enabled("stdio")
    assert not cfg.effective_downloads_enabled("http")
    on = load_config(env={"AMERIFLUX_MCP_DOWNLOADS__ENABLED": "true"})
    assert on.effective_downloads_enabled("stdio") and not on.effective_downloads_enabled("http")
    flag = load_config(env={}, flag_overrides={"downloads_enabled": True})
    assert flag.effective_downloads_enabled("stdio")
    assert cfg.downloads.directory.name == "ameriflux-downloads"
    assert cfg.local_roots() == [cfg.downloads.directory]


def test_disk_cache_is_stdio_only_unless_configured(tmp_path: Path) -> None:
    cfg = load_config(env={})
    assert cfg.effective_disk_cache("stdio") == Path("~/.cache/ameriflux-mcp").expanduser()
    assert cfg.effective_disk_cache("http") is None
    custom = load_config(env={"AMERIFLUX_MCP_CACHE__DISK_DIR": str(tmp_path)})
    assert custom.effective_disk_cache("http") == tmp_path.resolve()
    off = load_config(env={"AMERIFLUX_MCP_CACHE__ENABLED": "false"})
    assert off.effective_disk_cache("stdio") is None


def test_precedence_flag_over_env_over_yaml(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(
        "server:\n  bind_port: 9000\n  log_level: debug\nlimits:\n  max_result_bytes: 30000\n"
    )
    cfg = load_config(
        path, env={"AMERIFLUX_MCP_SERVER__BIND_PORT": "9100"}, flag_overrides={"log_level": "error"}
    )
    assert cfg.server.bind_port == 9100
    assert cfg.server.log_level == "error"
    assert cfg.limits.max_result_bytes == 30_000


def test_env_nesting_lists_and_nulls(tmp_path: Path) -> None:
    cfg = load_config(
        env={
            "AMERIFLUX_MCP_UPSTREAM__RETRIES__MAX_ATTEMPTS": "5",
            "AMERIFLUX_MCP_CACHE__TTL_S__CATALOG": "60",
            "AMERIFLUX_MCP_SERVER__ALLOWED_HOSTS": "a.example, b.example",
            "AMERIFLUX_MCP_LOCAL__ROOTS": f"{tmp_path}/a, {tmp_path}/b",
            "AMERIFLUX_MCP_DOWNLOADS__ENABLED": "false",
            "AMERIFLUX_MCP_SERVER__PUBLIC_BASE_URL": "none",
        }
    )
    assert cfg.upstream.retries.max_attempts == 5
    assert cfg.cache.ttl_s.catalog == 60
    assert cfg.server.allowed_hosts == ["a.example", "b.example"]
    assert cfg.local.roots == [(tmp_path / "a").resolve(), (tmp_path / "b").resolve()]
    assert cfg.local_roots()[1:] == cfg.local.roots
    assert cfg.downloads.enabled is False
    assert cfg.server.public_base_url is None
    assert not cfg.effective_downloads_enabled("stdio")


def test_plain_identity_variables() -> None:
    cfg = load_config(env=IDENTITY_ENV)
    ident = cfg.identity
    assert ident.user_id is not None and ident.user_id.get_secret_value() == "fluxtester42"
    assert ident.user_email is not None
    assert ident.user_email.get_secret_value() == "flux.tester@example.org"
    assert ident.user_name is not None and ident.user_name.get_secret_value() == "Flux Tester"
    assert ident.is_test is True
    default = ident.profiles["default"]
    assert default.intended_use == "other_research"
    assert default.description == IDENTITY_ENV["AMERIFLUX_DESCRIPTION"]


def test_namespaced_identity_wins_over_plain() -> None:
    cfg = load_config(
        env={
            "AMERIFLUX_USER_ID": "plain-user",
            "AMERIFLUX_MCP_IDENTITY__USER_ID": "namespaced-user",
            "AMERIFLUX_INTENDED_USE": "1",
            "AMERIFLUX_MCP_IDENTITY__PROFILES__DEFAULT__INTENDED_USE": "education",
        }
    )
    assert cfg.identity.user_id is not None
    assert cfg.identity.user_id.get_secret_value() == "namespaced-user"
    assert cfg.identity.profiles["default"].intended_use == "education"


def test_yaml_profiles_and_env_default(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(
        "identity:\n  profiles:\n    teaching:\n      intended_use: 5\n"
        "      description: Classroom exercises on energy-balance closure.\n"
    )
    cfg = load_config(path, env={"AMERIFLUX_INTENDED_USE": "remote_sensing"})
    assert cfg.identity.profiles["teaching"].intended_use == "education"
    assert cfg.identity.profiles["default"].intended_use == "remote_sensing"
    assert cfg.identity.profiles["default"].description is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", "synthesis"), ("6", "other"), ("Model", "model"), (" 3 ", "remote_sensing")],
)
def test_intended_use_codes(raw: str, expected: str) -> None:
    assert load_config(env={"AMERIFLUX_INTENDED_USE": raw}).identity.profiles[
        "default"
    ].intended_use == (expected)


@pytest.mark.parametrize(
    ("env", "field"),
    [
        ({"AMERIFLUX_USER_EMAIL": "not-an-email-secret"}, "identity.user_email"),
        ({"AMERIFLUX_INTENDED_USE": "9"}, "intended_use"),
        ({"AMERIFLUX_DESCRIPTION": "too short"}, "description"),
        ({"AMERIFLUX_DESCRIPTION": "x" * 1001}, "description"),
        ({"AMERIFLUX_MCP_IDENTITY__IS_TEST": "maybe"}, "identity.is_test"),
    ],
)
def test_invalid_identity_never_echoes_values(env: dict[str, str], field: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(env=env)
    text = str(exc.value)
    assert field in text
    assert "not-an-email-secret" not in text and "too short" not in text and "maybe" not in text


def test_blank_identity_values_count_as_unset() -> None:
    cfg = load_config(env={"AMERIFLUX_USER_ID": "   ", "AMERIFLUX_MCP_IDENTITY__USER_EMAIL": ""})
    assert cfg.identity.user_id is None and cfg.identity.user_email is None


def test_identity_never_rendered() -> None:
    cfg = load_config(env=IDENTITY_ENV)
    text = repr(cfg) + str(cfg.model_dump())
    dumped = cfg.model_dump_redacted()
    assert dumped["identity"]["user_id"] == dumped["identity"]["user_email"] == "***"
    assert dumped["identity"]["user_name"] == "***"
    for value in PRIVATE_VALUES:
        assert value not in text and value not in str(dumped)
    assert load_config(env={}).model_dump_redacted()["identity"]["user_id"] is None


def test_lookalike_identity_names_warn_and_are_ignored(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="ameriflux_mcp.config"):
        cfg = load_config(env={"AMERIFLUX_EMAIL": "leak@example.org", "AMF_USER_ID": "leaky-user"})
    assert cfg.identity.user_email is None and cfg.identity.user_id is None
    assert "AMERIFLUX_EMAIL is set" in caplog.text and "AMF_USER_ID is set" in caplog.text
    assert "leak@example.org" not in caplog.text and "leaky-user" not in caplog.text


def test_unknown_keys_warn(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(
        "upstream:\n  bogus: 1\nnope: {}\ncache:\n  ttl_s:\n    nada: 5\n"
        "identity:\n  profiles:\n    default:\n      purpose: x\n"
    )
    with caplog.at_level(logging.WARNING, logger="ameriflux_mcp.config"):
        load_config(path, env={"AMERIFLUX_MCP_SERVER__NOPE": "1"})
    text = caplog.text
    for key in (
        "upstream.bogus",
        "'nope'",
        "cache.ttl_s.nada",
        "server.nope",
        "identity.profiles.default.purpose",
    ):
        assert key in text


def test_empty_yaml_sections_count_as_absent(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("cache:\n  # disk_dir: x\nidentity:\nupstream:\n  retries:\n")
    cfg = load_config(path, env={})
    assert cfg.cache.enabled is True and cfg.upstream.retries.max_attempts == 3


def test_example_config_loads() -> None:
    example = Path(__file__).resolve().parent.parent / "config.yaml.example"
    cfg = load_config(example, env={})
    assert cfg.identity.profiles["default"].intended_use == "other_research"
    assert cfg.identity.user_id is None and cfg.identity.is_test is None


def test_download_dir_is_expanded() -> None:
    cfg = load_config(env={}, flag_overrides={"download_dir": "~/amf-x"})
    assert cfg.downloads.directory.is_absolute()
    assert "~" not in str(cfg.downloads.directory)
    assert load_config(env={}).downloads.directory.is_absolute()


def test_invalid_values_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"server\.transport"):
        load_config(env={"AMERIFLUX_MCP_SERVER__TRANSPORT": "sse"})
    path = tmp_path / "c.yaml"
    path.write_text("- not\n- a mapping\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(path, env={})
    with pytest.raises(KeyError):
        load_config(env={}, flag_overrides={"user_id": "x"})


def test_active_config_roundtrip() -> None:
    cfg = Config()
    set_active_config(cfg)
    try:
        assert get_active_config() is cfg
    finally:
        set_active_config(None)
    assert isinstance(get_active_config(), Config)


def test_empty_env_values_count_as_unset() -> None:
    cfg = load_config(
        env={
            "AMERIFLUX_MCP_SERVER__ALLOWED_HOSTS": "",
            "AMERIFLUX_MCP_SERVER__PUBLIC_BASE_URL": "  ",
            "AMERIFLUX_MCP_SERVER__INSTRUCTIONS_EXTRA": "null",
        }
    )
    assert cfg.server.allowed_hosts == [] and cfg.server.public_base_url is None
    assert cfg.server.instructions_extra is None
