"""scripts/install.sh: agent config edits in a sandboxed HOME, and identity never printed.

The script runs with an empty HOME, a PATH holding only basic tools (no agent CLIs, so
every agent goes through its config file) and ``--command`` pointing at a stub server
that answers ``--version``, so it needs no network, no package install and never touches
the developer's real agent configs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "install.sh"
TOOLS = ("bash", "uname", "dirname", "sed", "grep", "head", "tr", "cat")
IDENTITY = {
    "AMERIFLUX_USER_ID": "fluxtester42",
    "AMERIFLUX_USER_EMAIL": "flux.tester@example.org",
    "AMERIFLUX_USER_NAME": "Flux Tester",
    "AMERIFLUX_INTENDED_USE": "4",
    "AMERIFLUX_DESCRIPTION": "Testing the installer in a sandbox; not a real request.",
    "AMERIFLUX_MCP_IDENTITY__IS_TEST": "true",
}
PRIVATE = ("fluxtester42", "flux.tester@example.org", "Flux Tester")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="needs a POSIX bash"
)


def stub_server(path: Path, exit_code: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "ameriflux-mcp 0.1.0"\nexit {exit_code}\n')
    path.chmod(0o755)
    return path


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found, tool
        (bin_dir / tool).symlink_to(found)
    stub_server(tmp_path / "server" / "ameriflux-mcp")
    return tmp_path


def server(sandbox: Path) -> str:
    return str(sandbox / "server" / "ameriflux-mcp")


def run(
    sandbox: Path,
    *args: str,
    identity: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
    command: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        "HOME": str(sandbox / "home"),
        "PATH": str(sandbox / "bin"),
        "AMERIFLUX_INSTALL_PYTHON": sys.executable,
        **(identity or {}),
        **(extra or {}),
    }
    cmd = command or server(sandbox)
    return subprocess.run(
        [shutil.which("bash") or "bash", str(SCRIPT), "--command", cmd, "--no-sync", *args],
        env=env,
        cwd=sandbox,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def paths(sandbox: Path) -> dict[str, Path]:
    home = sandbox / "home"
    desktop = (
        home / "Library/Application Support/Claude/claude_desktop_config.json"
        if sys.platform == "darwin"
        else home / ".config/Claude/claude_desktop_config.json"
    )
    return {
        "claude-desktop": desktop,
        "codex": home / ".codex/config.toml",
        "gemini": home / ".gemini/settings.json",
        "goose": home / ".config/goose/config.yaml",
        "opencode": home / ".config/opencode/opencode.json",
    }


def seed(sandbox: Path) -> dict[str, Path]:
    """Pre-existing configs, each with an unrelated entry that must survive."""
    p = paths(sandbox)
    for path in p.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    p["claude-desktop"].write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    p["gemini"].write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    p["codex"].write_text('model = "o4"\n\n[mcp_servers.other]\ncommand = "x"\n')
    p["goose"].write_text(
        "GOOSE_PROVIDER: openai\nextensions:\n  developer:\n    enabled: true\n    type: builtin\n"
    )
    p["opencode"].write_text(json.dumps({"mcp": {"servers": {"other": {"type": "local"}}}}))
    return p


def entries(p: dict[str, Path]) -> dict[str, dict[str, object]]:
    goose = yaml.safe_load(p["goose"].read_text())
    return {
        "claude-desktop": json.loads(p["claude-desktop"].read_text())["mcpServers"],
        "gemini": json.loads(p["gemini"].read_text())["mcpServers"],
        "codex": tomllib.loads(p["codex"].read_text())["mcp_servers"],
        "goose": goose["extensions"],
        "opencode": json.loads(p["opencode"].read_text())["mcp"]["servers"],
    }


def assert_private(text: str) -> None:
    for value in PRIVATE:
        assert value not in text, value


def test_install_with_identity_writes_every_config_and_never_prints_it(sandbox: Path) -> None:
    p = seed(sandbox)
    srv = server(sandbox)
    result = run(sandbox, "--agents", "all", "--with-identity", identity=IDENTITY)
    assert result.returncode == 0, result.stderr
    assert_private(result.stdout + result.stderr)
    assert "ameriflux-mcp 0.1.0" in result.stdout
    found = entries(p)
    for agent, servers in found.items():
        assert "other" in servers or "developer" in servers, agent
    assert found["claude-desktop"]["ameriflux"] == {"command": srv, "args": [], "env": IDENTITY}
    assert found["gemini"]["ameriflux"]["env"] == IDENTITY  # type: ignore[index]
    assert found["codex"]["ameriflux"] == {"command": srv, "args": [], "env": IDENTITY}
    assert found["goose"]["ameriflux"]["cmd"] == srv  # type: ignore[index]
    assert found["goose"]["ameriflux"]["envs"] == IDENTITY  # type: ignore[index]
    assert found["opencode"]["ameriflux"] == {
        "type": "local",
        "command": [srv],
        "environment": IDENTITY,
    }
    assert json.loads(p["gemini"].read_text())["theme"] == "dark"
    assert tomllib.loads(p["codex"].read_text())["model"] == "o4"
    for path in p.values():
        assert Path(f"{path}.bak").exists()
        assert path.stat().st_mode & 0o077 == 0  # holds the identity: owner-only


def test_name_is_optional(sandbox: Path) -> None:
    ident = {k: v for k, v in IDENTITY.items() if k != "AMERIFLUX_USER_NAME"}
    result = run(sandbox, "--agents", "codex", "--with-identity", identity=ident)
    assert result.returncode == 0, result.stderr
    codex = tomllib.loads(paths(sandbox)["codex"].read_text())["mcp_servers"]["ameriflux"]
    assert codex["env"] == ident


def test_backups_of_identity_bearing_files_stay_owner_only(sandbox: Path) -> None:
    p = seed(sandbox)
    for path in p.values():
        path.chmod(0o644)
    assert run(sandbox, "--agents", "all", "--with-identity", identity=IDENTITY).returncode == 0
    again = run(sandbox, "--agents", "all", "--with-identity", "--env", "X=1", identity=IDENTITY)
    assert again.returncode == 0, again.stderr
    for path in p.values():
        bak = Path(f"{path}.bak")
        assert IDENTITY["AMERIFLUX_USER_EMAIL"] in bak.read_text()
        assert bak.stat().st_mode & 0o077 == 0, bak
    assert run(sandbox, "--agents", "all", "--uninstall").returncode == 0
    for path in p.values():
        assert IDENTITY["AMERIFLUX_USER_EMAIL"] not in path.read_text()
        assert Path(f"{path}.bak").stat().st_mode & 0o077 == 0


def test_dry_run_writes_nothing_and_masks_identity(sandbox: Path) -> None:
    result = run(sandbox, "--agents", "all", "--with-identity", "--dry-run", identity=IDENTITY)
    assert result.returncode == 0, result.stderr
    assert_private(result.stdout + result.stderr)
    assert '"AMERIFLUX_USER_EMAIL": "***"' in result.stdout
    assert not any(path.exists() for path in paths(sandbox).values())


def test_without_identity_registers_no_env(sandbox: Path) -> None:
    p = paths(sandbox)
    result = run(sandbox, "--agents", "claude-desktop,codex", identity=IDENTITY)
    assert result.returncode == 0, result.stderr
    assert "Download identity: not stored" in result.stdout
    desktop = json.loads(p["claude-desktop"].read_text())["mcpServers"]["ameriflux"]
    assert desktop == {"command": server(sandbox), "args": []}
    assert IDENTITY["AMERIFLUX_USER_EMAIL"] not in p["codex"].read_text()


def test_rerun_is_idempotent_and_uninstall_removes_only_ameriflux(sandbox: Path) -> None:
    p = seed(sandbox)
    assert run(sandbox, "--agents", "all").returncode == 0
    again = run(sandbox, "--agents", "all")
    assert again.returncode == 0, again.stderr
    assert again.stdout.count("already up to date") == len(p)
    removed = run(sandbox, "--agents", "all", "--uninstall")
    assert removed.returncode == 0, removed.stderr
    for agent, servers in entries(p).items():
        assert "ameriflux" not in servers, agent
        assert servers, agent  # the unrelated entry is still there


@pytest.mark.parametrize(
    "name",
    [
        "AMERIFLUX_USER_ID",
        "AMERIFLUX_USER_EMAIL",
        "AMERIFLUX_USER_NAME",
        "AMERIFLUX_INTENDED_USE",
        "AMERIFLUX_DESCRIPTION",
        "AMERIFLUX_MCP_IDENTITY__IS_TEST",
        "AMERIFLUX_MCP_IDENTITY__USER_EMAIL",
    ],
)
def test_identity_cannot_be_passed_with_env(sandbox: Path, name: str) -> None:
    result = run(sandbox, "--agents", "codex", "--env", f"{name}=x")
    assert result.returncode == 2
    assert "--with-identity" in result.stderr
    assert not paths(sandbox)["codex"].exists()


def test_with_identity_needs_the_environment_or_a_terminal(sandbox: Path) -> None:
    partial = {k: v for k, v in IDENTITY.items() if k != "AMERIFLUX_DESCRIPTION"}
    result = run(sandbox, "--agents", "codex", "--with-identity", identity=partial)
    assert result.returncode == 2
    assert "AMERIFLUX_DESCRIPTION" in result.stderr
    assert not paths(sandbox)["codex"].exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("AMERIFLUX_USER_EMAIL", "not-an-email", "not an email address"),
        ("AMERIFLUX_INTENDED_USE", "9", "intended use must be 1-6"),
        ("AMERIFLUX_DESCRIPTION", "too short", "20-1000 characters"),
        ("AMERIFLUX_DESCRIPTION", "x" * 1001, "20-1000 characters"),
        ("AMERIFLUX_MCP_IDENTITY__IS_TEST", "maybe", "true or false"),
    ],
)
def test_identity_is_validated(sandbox: Path, field: str, value: str, message: str) -> None:
    result = run(
        sandbox, "--agents", "codex", "--with-identity", identity={**IDENTITY, field: value}
    )
    assert result.returncode == 2
    assert message in result.stderr
    assert "not-an-email" not in result.stderr  # the bad value is not echoed
    assert not paths(sandbox)["codex"].exists()


def test_intended_use_accepts_keys(sandbox: Path) -> None:
    ident = {**IDENTITY, "AMERIFLUX_INTENDED_USE": "remote_sensing"}
    result = run(sandbox, "--agents", "codex", "--with-identity", identity=ident)
    assert result.returncode == 0, result.stderr


def test_a_server_that_does_not_start_is_not_registered(sandbox: Path) -> None:
    broken = str(stub_server(sandbox / "broken" / "ameriflux-mcp", exit_code=1))
    result = run(sandbox, "--agents", "claude-desktop,codex", command=broken)
    assert result.returncode == 1
    assert "nothing was registered" in result.stderr
    assert not any(path.exists() for path in paths(sandbox).values())

    preview = run(sandbox, "--agents", "codex", "--dry-run", command=broken)
    assert preview.returncode == 0, preview.stderr
    assert "a real install would stop here" in preview.stderr

    forced = run(sandbox, "--agents", "codex", "--no-verify", command=broken)
    assert forced.returncode == 0, forced.stderr
    assert paths(sandbox)["codex"].exists()


def test_missing_command_is_not_registered(sandbox: Path) -> None:
    result = run(sandbox, "--agents", "codex", command=str(sandbox / "nope" / "ameriflux-mcp"))
    assert result.returncode == 1
    assert not paths(sandbox)["codex"].exists()


def test_extra_env_and_unknown_agent(sandbox: Path) -> None:
    result = run(
        sandbox, "--agents", "codex,nope", "--env", "AMERIFLUX_MCP_SERVER__LOG_LEVEL=debug"
    )
    assert result.returncode == 1
    assert "unknown agent 'nope'" in result.stdout
    codex = tomllib.loads(paths(sandbox)["codex"].read_text())["mcp_servers"]["ameriflux"]
    assert codex["env"] == {"AMERIFLUX_MCP_SERVER__LOG_LEVEL": "debug"}


def test_help_lists_every_agent_and_option(sandbox: Path) -> None:
    result = run(sandbox, "--help")
    assert result.returncode == 0
    for word in ("claude", "claude-desktop", "codex", "gemini", "goose", "opencode"):
        assert word in result.stdout
    for option in ("--with-identity", "--no-verify", "--uninstall", "-h, --help"):
        assert option in result.stdout
    assert os.access(SCRIPT, os.X_OK)


STUB = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$STUB_LOG"
if [ "$2" = get ]; then exit "${STUB_GET_EXIT:-1}"; fi
echo "stored: $*"
"""


@pytest.mark.parametrize("registered", [False, True])
def test_agent_clis_get_identity_in_env_args_and_their_output_is_masked(
    sandbox: Path, registered: bool
) -> None:
    log = sandbox / "argv.log"
    for cli in ("claude", "codex", "gemini"):
        stub = sandbox / "bin" / cli
        stub.write_text(STUB)
        stub.chmod(0o755)
    extra = {"STUB_LOG": str(log), "STUB_GET_EXIT": "0" if registered else "1"}
    ident = {k: v for k, v in IDENTITY.items() if k != "AMERIFLUX_USER_NAME"}
    result = run(
        sandbox,
        "--agents",
        "claude,codex,gemini",
        "--with-identity",
        identity=ident,
        extra=extra,
    )
    assert result.returncode == 0, result.stderr
    assert_private(result.stdout + result.stderr)
    assert "stored:" in result.stdout  # the CLIs' own output is shown, masked
    calls = [line.split(" ", 1)[1] for line in log.read_text().splitlines()]
    adds = [c for c in calls if " add " in f" {c} "]
    srv = server(sandbox)
    claude_env = " ".join(f"-e {k}={v}" for k, v in ident.items())
    codex_env = " ".join(f"--env {k}={v}" for k, v in ident.items())
    assert f"mcp add --scope user ameriflux {claude_env} -- {srv}" in adds
    assert f"mcp add ameriflux {codex_env} -- {srv}" in adds
    assert f"mcp add --scope user --transport stdio {claude_env} ameriflux {srv}" in adds
    removes = [c for c in calls if c.startswith("mcp remove")]
    assert removes == (
        ["mcp remove --scope user ameriflux", "mcp remove ameriflux"] if registered else []
    )
    assert not any(path.exists() for path in paths(sandbox).values())  # CLIs, not files


def test_agent_cli_uninstall(sandbox: Path) -> None:
    log = sandbox / "argv.log"
    for cli in ("claude", "codex", "gemini"):
        stub = sandbox / "bin" / cli
        stub.write_text(STUB)
        stub.chmod(0o755)
    result = run(
        sandbox, "--agents", "claude,codex,gemini", "--uninstall", extra={"STUB_LOG": str(log)}
    )
    assert result.returncode == 0, result.stderr
    calls = [line.split(" ", 1)[1] for line in log.read_text().splitlines()]
    assert calls == [
        "mcp remove --scope user ameriflux",
        "mcp remove ameriflux",
        "mcp remove --scope user ameriflux",
    ]
