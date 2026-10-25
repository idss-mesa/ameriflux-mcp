"""Release metadata (build step 8): versions agree, server.json is valid, images and workflows are safe."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import jsonschema
import yaml

from ameriflux_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]
SERVER_JSON = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _workflow(name: str) -> dict[str, object]:
    data = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # PyYAML reads the bare key `on` as True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def test_readme_mcp_name_matches_server_json() -> None:
    """PyPI ownership verification for the MCP registry (D29)."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    names = re.findall(r"<!-- mcp-name: (\S+) -->", readme)
    assert names == [SERVER_JSON["name"]] == ["io.github.idss-mesa/ameriflux-mcp"]


def test_versions_agree() -> None:
    assert PROJECT["dynamic"] == ["version"]  # read from ameriflux_mcp.__version__
    assert __version__ == SERVER_JSON["version"]
    (package,) = SERVER_JSON["packages"]
    assert package["identifier"] == PROJECT["name"] and package["version"] == __version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog


def test_server_json_validates_against_the_registry_schema() -> None:
    schema = json.loads(
        (ROOT / "tests" / "data" / "server.schema.2025-12-11.json").read_text(encoding="utf-8")
    )
    assert SERVER_JSON["$schema"].endswith("/2025-12-11/server.schema.json")
    jsonschema.validate(SERVER_JSON, schema)


def test_server_json_lists_only_names_the_server_reads() -> None:
    from ameriflux_mcp.config import IDENTITY_ENV_FALLBACKS, PROFILE_ENV_FALLBACKS, load_config

    names = [v["name"] for v in SERVER_JSON["packages"][0]["environmentVariables"]]
    plain = set(IDENTITY_ENV_FALLBACKS.values()) | set(PROFILE_ENV_FALLBACKS.values())
    for name in names:
        assert name in plain or name.startswith("AMERIFLUX_MCP_"), name
    secrets = {
        v["name"] for v in SERVER_JSON["packages"][0]["environmentVariables"] if v.get("isSecret")
    }
    assert secrets == set(IDENTITY_ENV_FALLBACKS.values())
    # Every namespaced name maps onto a real setting (no unknown-key warning).
    env = {n: "x" for n in names if n.startswith("AMERIFLUX_MCP_") and "IS_TEST" not in n}
    env["AMERIFLUX_MCP_IDENTITY__IS_TEST"] = "true"
    load_config(env=env)


def test_dockerfile_is_pinned_and_unprivileged() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "uv:latest" not in text and re.search(r"astral-sh/uv:\d+\.\d+\.\d+", text)
    assert "--uid 10001" in text and "\nUSER ameriflux" in text
    assert "--frozen --no-dev" in text and "--extra" not in text
    assert "AMERIFLUX_MCP_SERVER__TRANSPORT=http" in text
    assert "IDENTITY" not in text and "AMERIFLUX_USER" not in text
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert ".env" in ignored and ".git" in ignored


def test_release_workflow_uses_trusted_publishing() -> None:
    wf = _workflow("release.yml")
    assert wf["on"] == {"push": {"tags": ["v*"]}}
    job = wf["jobs"]["build-and-publish"]  # type: ignore[index]
    assert job["environment"] == "pypi"
    assert wf["permissions"]["id-token"] == "write"  # type: ignore[index]
    steps = json.dumps(job["steps"])
    assert "pypa/gh-action-pypi-publish" in steps and "server.json" in steps
    assert "secrets." not in steps  # no API token: trusted publishing only


def test_only_the_manual_workflow_can_post() -> None:
    live = _workflow("live-download.yml")
    assert set(live["on"]) == {"workflow_dispatch"}  # type: ignore[arg-type]
    assert live["jobs"]["live-download"]["environment"] == "live-download"  # type: ignore[index]
    for name in ("ci.yml", "docs.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "live_download" not in text and "AMERIFLUX_USER" not in text, name
