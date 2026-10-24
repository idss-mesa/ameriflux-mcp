"""amf_get_badm against the recorded fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import call_err, call_ok


async def badm(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_get_badm", args)


async def test_full_record(server: AmeriFluxServer) -> None:
    payload = await badm(server, site="US-Ha1")
    assert payload["siteId"] == "US-Ha1" and payload["policy"] == "CCBY4.0"
    site = payload["site"]
    assert site["igbp"] == "DBF" and site["koeppen"] == "Dfb" and site["latitude"] == 42.5378
    assert payload["team"][0]["role"] == "PI" and "email" not in payload["team"][0]
    assert payload["disturbance"] == ["Undisturbed"] and "CO2" in payload["fluxMeasurements"]
    funding = payload["funding"]
    assert funding["sponsors"] == ["DOE/TES (AmeriFlux Core site), NSF/LTER"]
    assert funding["organizations"] == ["Harvard University"] and funding["doi"]
    refs = payload["references"]
    assert refs["page"]["total"] == 4 and refs["items"][0]["doi"]  # fixture keeps 4 of 60
    instruments = payload["instruments"]
    assert instruments["date"] == "2026-09-08" and instruments["total"] == len(instruments["items"])
    assert any(i["variable"] == "TA_1_1_1" and i["heightM"] == 27.9 for i in instruments["items"])
    assert any("BIF file" in n for n in payload["notes"])
    assert payload["source"]["backend"] == "mixed"
    assert "@" not in json.dumps(payload)


async def test_sections_and_filters(server: AmeriFluxServer, router: FixtureRouter) -> None:
    funding = await badm(server, site="US-Ha1", include=["funding"])
    assert "site" not in funding and "instruments" not in funding and funding["funding"]
    assert not router.calls_to("/data/measurement-height/")
    ta = await badm(server, site="US-Ha1", include=["instruments"], variables=["ta", "P"])
    names = {i["variable"] for i in ta["instruments"]["items"]}
    assert "P" in names and "TA_1_1_1" in names and "TA_PI_F_1_1_1" in names
    assert not any(n.startswith(("PA", "PPFD", "P_RAIN")) for n in names)
    exact = await badm(server, site="US-Ha1", include=["instruments"], variables=["TA_1_2_1"])
    assert [i["variable"] for i in exact["instruments"]["items"]] == ["TA_1_2_1"]
    refs = await badm(server, site="US-Ha1", include=["references"], references_limit=2)
    assert refs["references"]["page"]["nextOffset"] == 2
    assert any("references_offset=2" in s for s in refs["nextSteps"])


async def test_legacy_site_without_sponsor(server: AmeriFluxServer) -> None:
    payload = await badm(server, site="ca-let")
    assert payload["policy"] == "LEGACY" and payload["funding"]["sponsors"] == []
    assert any("GRP_ACKNOWLEDGEMENT" in n for n in payload["notes"])
    assert all(m.get("institution") != "" for m in payload["team"])


async def test_fluxnet_only_site(server: AmeriFluxServer, router: FixtureRouter) -> None:
    payload = await badm(server, site="DE-Tha")
    assert payload["funding"]["doi"].startswith("10.18140/FLX/")
    assert router.calls_to("/api/v1/DOI/DE-Tha/FLUXNET2015")
    assert "instruments" not in payload
    assert any("only for AmeriFlux BASE sites" in n for n in payload["notes"])
    assert not router.calls_to("/data/measurement-height/")


async def test_missing_sources_become_notes(
    make_server: Callable[..., AmeriFluxServer], config: Config, router: FixtureRouter
) -> None:
    cfg = config.model_copy(deep=True)
    cfg.upstream.retries.max_attempts = 1
    server = make_server(config=cfg)
    router.add("GET amfcdn.lbl.gov/api/v1/DOI/US-Ha1/AmeriFlux", Reply(503, b"x", "text/plain"))
    router.add("GET ameriflux.lbl.gov/data/measurement-height/", Reply(404, b"gone", "text/html"))
    payload = await badm(server, site="US-Ha1")
    assert "funding" not in payload and "references" not in payload and "instruments" not in payload
    notes = " ".join(payload["notes"])
    assert "DOI record was unavailable" in notes and "Measurement heights unavailable" in notes
    assert payload["site"]["igbp"] == "DBF"


async def test_contacts_need_both_flags(
    make_server: Callable[..., AmeriFluxServer], config: Config, tmp_path: Path
) -> None:
    cfg = config.model_copy(deep=True)
    cfg.privacy.allow_contact_emails = True
    cfg.cache.disk_dir = tmp_path / "fresh-cache"
    server = make_server(config=cfg)
    shown = await badm(server, site="US-Ha1", include=["team"], include_contacts=True)
    assert all(m["email"].endswith("@example.org") for m in shown["team"])
    hidden = await badm(server, site="US-Ha1", include=["team"])
    assert all("email" not in m for m in hidden["team"])


async def test_contacts_withheld_note(server: AmeriFluxServer) -> None:
    payload = await badm(server, site="US-Ha1", include=["team"], include_contacts=True)
    assert all("email" not in m for m in payload["team"])
    assert any("withheld" in n for n in payload["notes"])


async def test_errors(server: AmeriFluxServer) -> None:
    await call_err(server, "amf_get_badm", {"site": "Harvard Forest"}, "ambiguous_input")
    await call_err(server, "amf_get_badm", {"site": "US-Ha1", "include": ["x"]}, "invalid_argument")
