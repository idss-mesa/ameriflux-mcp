"""The generated documentation is current, deterministic and complete (as neon-mcp)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import ameriflux_mcp.tools  # noqa: F401  (registers every tool)
from ameriflux_mcp.prompts import PROMPTS
from ameriflux_mcp.registry import get_registered_tools
from ameriflux_mcp.resources import known_uris

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_reference_is_current() -> None:
    result = _run("scripts/gen_tools_reference.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_config_reference_is_current() -> None:
    result = _run("scripts/gen_config_reference.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_generation_is_deterministic() -> None:
    tools = _load("gen_tools_reference")
    assert tools.render() == tools.render()
    config = _load("gen_config_reference")
    assert config.render() == config.render()


def test_reference_and_family_pages_cover_every_tool() -> None:
    reference = (ROOT / "docs/tools/reference.md").read_text(encoding="utf-8")
    family = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "docs/tools").glob("*.md")
        if p.name not in ("reference.md", "index.md", "roadmap.md")
    )
    specs = get_registered_tools()
    assert len(specs) == 12
    for spec in specs:
        assert f"## {spec.name}\n" in reference, spec.name
        assert spec.name in family, f"{spec.name} is not described on any family page"


def test_prompts_and_guides_are_documented() -> None:
    docs = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "docs").rglob("*.md"))
    for prompt in PROMPTS:
        assert prompt.name in docs, prompt.name
    for uri in known_uris():
        if uri.startswith("ameriflux://guide/"):
            assert uri in docs, uri


def test_okf_bundle_is_valid() -> None:
    result = _run("scripts/okf_validate.py", "docs")
    assert result.returncode == 0, result.stdout
