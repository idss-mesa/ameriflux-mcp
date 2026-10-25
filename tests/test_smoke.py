from __future__ import annotations

import json
import socket
from importlib.metadata import entry_points
from typing import Any

import pytest

import ameriflux_mcp
from ameriflux_mcp import __main__ as cli
from tests.helpers import IDENTITY_ENV, PRIVATE_VALUES


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> pytest.MonkeyPatch:
    import os

    for name in list(os.environ):
        if name.startswith(("AMERIFLUX_", "AMF_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AMERIFLUX_MCP_DOWNLOADS__DIRECTORY", str(tmp_path / "dl"))
    monkeypatch.setenv("AMERIFLUX_MCP_CACHE__DISK_DIR", str(tmp_path / "cache"))
    return monkeypatch


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail on any outbound connection (asyncio's own socketpair still works)."""

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_version_and_entry_point() -> None:
    assert ameriflux_mcp.__version__ == "0.1.0"
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("ameriflux-mcp") == "ameriflux_mcp.__main__:main"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "ameriflux-mcp 0.1.0" in capsys.readouterr().out


def test_print_config_redacts_identity(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in IDENTITY_ENV.items():
        clean_env.setenv(name, value)
    assert cli.main(["--print-config", "--transport", "http", "--no-downloads"]) == 0
    out = capsys.readouterr().out
    for value in PRIVATE_VALUES:
        assert value not in out
    assert "user_id: '***'" in out and "user_email: '***'" in out
    assert "transport: http" in out


def test_check_without_identity_is_offline(
    clean_env: pytest.MonkeyPatch, no_network: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--check", "--log-level", "error"]) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report == {
        "ok": True,
        "version": "0.1.0",
        "protocolVersion": "2026-07-28",
        "transport": "stdio",
        "identityConfigured": False,
        "downloadsEnabled": False,
    }


def test_downloads_flag_enables_and_conflicts(
    clean_env: pytest.MonkeyPatch, no_network: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--check", "--log-level", "error", "--downloads"]) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["downloadsEnabled"] is True
    with pytest.raises(SystemExit) as exc:
        cli.main(["--check", "--downloads", "--no-downloads"])
    assert exc.value.code == 2


def test_check_with_identity_never_prints_it(
    clean_env: pytest.MonkeyPatch, no_network: None, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in IDENTITY_ENV.items():
        clean_env.setenv(name, value)
    assert cli.main(["--check", "--log-level", "debug"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out.strip().splitlines()[-1])
    assert report["identityConfigured"] is True
    for value in PRIVATE_VALUES:
        assert value not in captured.out + captured.err


def test_check_over_http_reports_no_identity(
    clean_env: pytest.MonkeyPatch, no_network: None, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in IDENTITY_ENV.items():
        clean_env.setenv(name, value)
    assert cli.main(["--check", "--transport", "http", "--log-level", "error"]) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["identityConfigured"] is False and report["downloadsEnabled"] is False


def test_invalid_config_exits_2_without_echoing_values(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clean_env.setenv("AMERIFLUX_USER_EMAIL", "no-at-sign-private")
    assert cli.main(["--check"]) == 2
    err = capsys.readouterr().err
    assert "identity.user_email" in err and "no-at-sign-private" not in err


def test_lookalike_variable_warns(
    clean_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clean_env.setenv("AMERIFLUX_EMAIL", "someone@example.org")
    assert cli.main(["--print-config"]) == 0
    captured = capsys.readouterr()
    assert "someone@example.org" not in captured.out + captured.err
