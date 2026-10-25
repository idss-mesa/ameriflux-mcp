"""A real, consented download (opt-in: ``AMERIFLUX_MCP_LIVE_DOWNLOAD=1``; DESIGN.md D11-D17).

This is the only test that POSTs to AmeriFlux. It runs from the manual
``live-download`` workflow (a protected environment with required reviewers; never on
a schedule or a pull request), with the maintainer's identity in that environment's
secrets and ``AMERIFLUX_MCP_IDENTITY__IS_TEST`` chosen at dispatch. It downloads one
small AmeriFlux FLUXNET zip (AR-Bal by default, ~22 MB), checks the integrity record
and that nothing written carries the identity, and prints the response's key sets
(never values) so RESEARCH.md can record the shape (Q4).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from ameriflux_mcp.ameriflux.downloads import read_sidecar, verify_archive
from ameriflux_mcp.config import load_config
from ameriflux_mcp.server import create_server

pytestmark = [
    pytest.mark.live_download,
    pytest.mark.skipif(
        os.environ.get("AMERIFLUX_MCP_LIVE_DOWNLOAD") != "1",
        reason="set AMERIFLUX_MCP_LIVE_DOWNLOAD=1 (manual workflow only)",
    ),
]
SITE = os.environ.get("AMERIFLUX_MCP_LIVE_SITE", "AR-Bal")


def _identity_values() -> list[str]:
    names = ("AMERIFLUX_USER_ID", "AMERIFLUX_USER_EMAIL", "AMERIFLUX_USER_NAME")
    return [os.environ[n] for n in names if os.environ.get(n, "").strip()]


async def test_one_consented_fluxnet_download(tmp_path: Path) -> None:
    assert re.fullmatch(r"[A-Za-z]{2}-[A-Za-z0-9]{3}", SITE), "AMERIFLUX_MCP_LIVE_SITE"
    config = load_config()
    config.downloads.directory = tmp_path / "downloads"
    config.cache.disk_dir = tmp_path / "cache"
    server = create_server(config, transport="stdio")
    args = {"sites": [SITE], "product": "FLUXNET"}

    plan = await server.call("amf_download_data", args)
    assert not plan.is_error, plan.payload
    assert plan.payload["ready"] is True, plan.payload["blockers"]
    code = plan.payload["policy"]["code"]

    done = await server.call(
        "amf_download_data", {**args, "accept_data_policy": code, "confirm": True}
    )
    assert not done.is_error, done.payload
    payload = done.payload
    print("files:", [(f["name"], f["status"], f.get("bytes")) for f in payload["files"]])
    print("skipped:", [(s["name"], s["reason"]) for s in payload["skipped"]])
    print("manifest keys:", sorted(payload.get("manifest") or {}))
    downloaded = [f for f in payload["files"] if f["status"] == "downloaded"]
    assert downloaded, payload
    path = Path(downloaded[0]["path"])
    sidecar = read_sidecar(path)
    assert sidecar is not None and sidecar["sha256"] == downloaded[0]["sha256"]
    verify_archive(path, max_member_bytes=config.limits.zip_member_max_bytes)

    written = "\n".join(
        p.read_text(encoding="utf-8") for p in config.downloads.directory.rglob("*.json")
    )
    blob = json.dumps(payload) + written
    for value in _identity_values():
        assert value not in blob
    assert "@" not in written

    preview = await server.call(
        "amf_preview_data", {"file": str(path), "resolution": "DD", "columns": ["NEE_VUT_REF"]}
    )
    assert not preview.is_error, preview.payload
    assert preview.payload["fileInfo"]["stepMinutes"] == 1440
    await server.aclose()
