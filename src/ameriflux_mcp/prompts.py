"""MCP prompts: task recipes that steer an agent through the tools.

The recipes (find_flux_sites, plan_site_analysis, cite_flux_data) arrive in build step 8,
once the tools they name exist. Until then the server answers prompts/list with an empty
list, so clients see the capability without stale recipes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mcp import types as t

from ameriflux_mcp.errors import ToolError


@dataclass(frozen=True)
class _Prompt:
    name: str
    title: str
    description: str


PROMPTS: tuple[_Prompt, ...] = ()


def list_prompts() -> list[t.Prompt]:
    return [t.Prompt(name=p.name, title=p.title, description=p.description) for p in PROMPTS]


def get_prompt(name: str, arguments: Mapping[str, str] | None = None) -> t.GetPromptResult:
    del arguments
    raise ToolError("not_found", f"Unknown prompt {name!r}.", details={"name": name})
