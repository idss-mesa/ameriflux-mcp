"""``ameriflux-mcp`` command line.

Flags > environment (``AMERIFLUX_MCP_*``, plus the plain ``AMERIFLUX_USER_*`` identity
names) > YAML (``--config``) > defaults. There is deliberately no flag for any
identity value: command lines leak into ``ps`` output and shell history.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ameriflux_mcp import __version__

if TYPE_CHECKING:
    from ameriflux_mcp.config import Config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ameriflux-mcp",
        description="MCP (2026-07-28) server for AmeriFlux and FLUXNET flux tower data. "
        "Bare `ameriflux-mcp` serves stdio.",
    )
    parser.add_argument("--config", type=Path, default=None, help="YAML config file.")
    parser.add_argument(
        "--transport", choices=("stdio", "http"), default=None, help="Transport (default stdio)."
    )
    parser.add_argument(
        "--bind-address", default=None, help="HTTP bind address (default 127.0.0.1)."
    )
    parser.add_argument(
        "--bind-port", type=int, default=None, help="HTTP bind port (default 8080)."
    )
    parser.add_argument(
        "--log-level", choices=("debug", "info", "warning", "error", "critical"), default=None
    )
    parser.add_argument(
        "--download-dir", type=Path, default=None, help="Directory downloads are confined to."
    )
    downloads = parser.add_mutually_exclusive_group()
    downloads.add_argument(
        "--downloads",
        action="store_true",
        help="Enable the download tool (stdio; off by default; same as "
        "AMERIFLUX_MCP_DOWNLOADS__ENABLED=true).",
    )
    downloads.add_argument("--no-downloads", action="store_true", help="Disable the download tool.")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the effective config (identity redacted) and exit.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Load config, call amf_ping in-process (no network), print a JSON report, exit 0/1.",
    )
    parser.add_argument("--version", action="version", version=f"ameriflux-mcp {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from ameriflux_mcp.config import ConfigError, load_config, set_active_config
    from ameriflux_mcp.logging import setup_logging

    overrides = {
        "transport": args.transport,
        "bind_address": args.bind_address,
        "bind_port": args.bind_port,
        "log_level": args.log_level,
        "download_dir": str(args.download_dir) if args.download_dir else None,
        "downloads_enabled": False if args.no_downloads else (True if args.downloads else None),
    }
    try:
        config = load_config(args.config, flag_overrides=overrides)
    except (ConfigError, OSError) as exc:
        print(f"ameriflux-mcp: {exc}", file=sys.stderr)
        return 2
    set_active_config(config)

    if args.print_config:
        import yaml

        yaml.safe_dump(config.model_dump_redacted(), sys.stdout, sort_keys=False)
        return 0

    setup_logging(config.server.log_level, transport=config.server.transport)
    if args.check:
        import asyncio

        return asyncio.run(_check(config))

    from ameriflux_mcp.server import run

    run(config, transport=config.server.transport)
    return 0


async def _check(config: Config) -> int:
    import json

    from ameriflux_mcp.server import create_server

    server = create_server(config, transport=config.server.transport)
    try:
        outcome = await server.call("amf_ping", {})
    finally:
        await server.aclose()
    payload = outcome.payload
    identity = payload.get("identity") or {}
    report: dict[str, Any] = {
        "ok": not outcome.is_error,
        "version": __version__,
        "protocolVersion": payload.get("protocolVersion"),
        "transport": payload.get("transport"),
        "identityConfigured": identity.get("available"),
        "downloadsEnabled": payload.get("downloadsEnabled"),
    }
    if outcome.is_error:
        report["problem"] = (payload.get("error") or {}).get("message")
    print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
