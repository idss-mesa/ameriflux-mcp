#!/usr/bin/env python3
"""Render docs/tools/reference.md from the live tool registry (no network).

Every registered tool gets a section: title, description, surface, identity
requirement, transports, annotations, upstream endpoints, an input table built
from the pydantic validation schema (by alias: the names clients send) and an
output-field table from the serialization schema. Tools are sorted by name,
so the output is deterministic.

``generated.at`` is kept from the existing file when the body is unchanged
(so CI's drift check is stable); when the body changes it becomes today's
date (UTC midnight) unless ``--generated-at`` is given.

Usage: python scripts/gen_tools_reference.py [--check] [--generated-at ISO]
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "docs" / "tools" / "reference.md"
sys.path.insert(0, str(ROOT / "src"))

from ameriflux_mcp import tools as _tools  # noqa: E402,F401  (registration)
from ameriflux_mcp.registry import get_registered_tools  # noqa: E402

#: Family pages arrive with their tools; until then families link to the roadmap.
FAMILY_PAGES: dict[str, str] = {
    "discovery": "discovery.md",
    "availability": "discovery.md",
    "variables": "variables.md",
    "citation": "citation.md",
    "metadata": "citation.md",
    "local": "local-files.md",
}


def _ref_name(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def _type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in schema:
        name = _ref_name(schema) or "object"
        target = defs.get(name, {})
        if "enum" in target:
            return " \\| ".join(f"`{v}`" for v in target["enum"])
        return name
    if "anyOf" in schema:
        parts = [_type(s, defs) for s in schema["anyOf"] if s.get("type") != "null"]
        nullable = any(s.get("type") == "null" for s in schema["anyOf"])
        return " \\| ".join(parts) + (" \\| null" if nullable else "")
    if "enum" in schema:
        return " \\| ".join(f"`{v}`" for v in schema["enum"])
    if "const" in schema:
        return f"`{schema['const']}`"
    kind = schema.get("type")
    if kind == "array":
        return f"array of {_type(schema.get('items', {}), defs)}"
    if (
        kind == "object"
        and "additionalProperties" in schema
        and isinstance(schema["additionalProperties"], dict)
    ):
        return f"object of {_type(schema['additionalProperties'], defs)}"
    return str(kind or "any")


def _constraints(schema: dict[str, Any]) -> str:
    target = schema
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        target = non_null[0] if len(non_null) == 1 else schema
    bits = []
    for key, label in (
        ("minimum", ">="),
        ("exclusiveMinimum", ">"),
        ("maximum", "<="),
        ("minLength", "min length"),
        ("maxLength", "max length"),
        ("minItems", "min items"),
        ("maxItems", "max items"),
    ):
        if key in target:
            bits.append(f"{label} {target[key]}")
    if "pattern" in target:
        bits.append(f"pattern `{target['pattern']}`")
    return "; ".join(bits)


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _default(schema: dict[str, Any]) -> str:
    if "default" not in schema:
        return ""
    value = schema["default"]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'`"{value}"`'
    return f"`{value}`"


def _stdio_note(specs: list[Any]) -> str:
    stdio_only = [s.name for s in specs if s.transports == frozenset({"stdio"})]
    if not stdio_only:
        return ""
    names = ", ".join(f"`{n}`" for n in stdio_only)
    return f"; {names} {'is' if len(stdio_only) == 1 else 'are'} offered only over stdio"


def render() -> str:
    lines: list[str] = []
    specs = get_registered_tools()
    lines.append("# Tool reference\n")
    lines.append(
        "Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. "
        f"{len(specs)} tools are registered{_stdio_note(specs)}. Inputs are snake_case and outputs "
        "camelCase. Every result also carries `resolved`, `notes`, `nextSteps` and `source` (whose "
        "`backend` says what answered: the AmeriFlux API, its file server, or nothing upstream), "
        "and failures return `structuredContent.error` with a stable `code`. Tools still to come "
        "are on the [roadmap](roadmap.md).\n"
    )
    lines.append("| Tool | Title | Family | Download identity |\n| --- | --- | --- | --- |")
    for spec in specs:
        page = FAMILY_PAGES.get(spec.surface, "roadmap.md")
        lines.append(
            f"| [`{spec.name}`](#{spec.name}) | {spec.title} | [{spec.surface}]({page}) | "
            f"{'required' if spec.requires_key else 'no'} |"
        )
    lines.append("")
    for spec in specs:
        in_schema = spec.input_model.model_json_schema(by_alias=True, mode="validation")
        out_schema = spec.output_model.model_json_schema(by_alias=True, mode="serialization")
        in_defs = in_schema.get("$defs", {})
        out_defs = out_schema.get("$defs", {})
        required = set(in_schema.get("required", []))
        lines.append(f"## {spec.name}\n")
        lines.append(f"**{spec.title}.** {spec.description}\n")
        key = "required (stdio only)" if spec.requires_key else "not needed"
        hints = ", ".join(
            f"{name}={str(value).lower()}"
            for name, value in (
                ("readOnly", spec.read_only),
                ("destructive", spec.destructive),
                ("idempotent", spec.idempotent),
                ("openWorld", spec.open_world),
            )
        )
        lines.append("| | |\n| --- | --- |")
        lines.append(f"| Surface | `{spec.surface}` |")
        lines.append(f"| Download identity | {key} |")
        lines.append(f"| Transports | {', '.join(sorted(spec.transports))} |")
        lines.append(f"| Annotations | {hints} |")
        if spec.supports_mrtr:
            lines.append("| Multi round-trip | may return `input_required` (elicitation) |")
        lines.append(
            f"| Upstream endpoints | {'<br>'.join(f'`{e}`' for e in spec.endpoints) or 'none'} |"
        )
        lines.append("")
        props = in_schema.get("properties", {})
        lines.append("**Inputs**\n")
        if props:
            lines.append(
                "| Name | Type | Required | Default | Description |\n| --- | --- | --- | --- | --- |"
            )
            for name, schema in props.items():
                desc = schema.get("description", "")
                extra = _constraints(schema)
                if extra:
                    desc = f"{desc} ({extra})" if desc else extra
                lines.append(
                    f"| `{name}` | {_cell(_type(schema, in_defs))} | {'yes' if name in required else ''} | "
                    f"{_cell(_default(schema))} | {_cell(desc)} |"
                )
        else:
            lines.append("None.")
        lines.append("")
        envelope = {"resolved", "notes", "nextSteps", "source"}
        out_props = {k: v for k, v in out_schema.get("properties", {}).items() if k not in envelope}
        lines.append("**Result fields** (besides the common envelope)\n")
        lines.append("| Field | Type | Description |\n| --- | --- | --- |")
        for name, schema in out_props.items():
            lines.append(
                f"| `{name}` | {_cell(_type(schema, out_defs))} | {_cell(schema.get('description', ''))} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


FRONT = """---
title: "Tool reference"
description: "Every ameriflux-mcp tool with its inputs, result fields, upstream endpoints and \
annotations, generated from the tool registry."
type: MCP Tool Reference
tags:
  - tools
  - reference
  - generated
generated:
  by: "process:gen_tools_reference"
  at: "{at}"
sources:
  - id: registry
    resource: "https://github.com/idss-mesa/ameriflux-mcp/tree/main/src/ameriflux_mcp/tools"
    title: "ameriflux-mcp tool registry"
    author: "team:idss-mesa"
status: stable
---

"""


def existing() -> tuple[str | None, str | None]:
    if not TARGET.exists():
        return None, None
    text = TARGET.read_text(encoding="utf-8")
    m = re.match(r"^---\n.*?\n  at: \"([^\"]+)\"\n.*?\n---\n\n(.*)$", text, re.DOTALL)
    return (m.group(1), m.group(2)) if m else (None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is out of date")
    parser.add_argument("--generated-at", default=None, help="ISO 8601 timestamp for generated.at")
    args = parser.parse_args()
    body = render()
    old_at, old_body = existing()
    if args.generated_at:
        at = args.generated_at
    elif old_body == body and old_at:
        at = old_at
    else:
        at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT00:00:00Z")
    text = FRONT.format(at=at) + body
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if old_body != body:
            print(
                "docs/tools/reference.md is out of date; run python scripts/gen_tools_reference.py"
            )
            return 1
        print("docs/tools/reference.md is up to date")
        return 0 if current else 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(
        f"wrote {TARGET.relative_to(ROOT)} ({len(get_registered_tools())} tools, {len(text)} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
