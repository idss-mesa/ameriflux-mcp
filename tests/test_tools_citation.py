"""amf_get_citation against the recorded fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from ameriflux_mcp.config import Config
from ameriflux_mcp.server import AmeriFluxServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import call_err, call_ok


async def cite(server: AmeriFluxServer, **args: Any) -> dict[str, Any]:
    return await call_ok(server, "amf_get_citation", args)


def by_site(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["siteId"]: c for c in payload["citations"]}


@pytest.fixture
def quick_server(make_server: Callable[..., AmeriFluxServer], config: Config) -> AmeriFluxServer:
    cfg = config.model_copy(deep=True)
    cfg.upstream.retries.max_attempts = 1
    return make_server(config=cfg)


async def test_base_citation_is_amerifluxs_own_text(server: AmeriFluxServer) -> None:
    payload = await cite(server, sites=["US-Ha1"])
    ha1 = by_site(payload)["US-Ha1"]
    assert ha1["source"] == "amfcdn" and ha1["version"] == "28-5" and ha1["year"] == "2026"
    assert (
        "Ver. 28-5, AmeriFlux AMP, (Dataset). https://doi.org/10.17190/AMF/1246059"
        in (ha1["citation"])
    )
    assert "bibtex" not in ha1
    assert payload["effectivePolicy"]["code"] == "CCBY4.0"
    assert [a["key"] for a in payload["acknowledgments"]] == ["doe_data_service"]
    assert payload["dataAvailability"]["statement"] == (
        "The AmeriFlux BASE data were accessed from [SOURCE] on XX Month YYYY"
    )
    assert "AmeriFlux APIs" in payload["dataAvailability"]["sourceOptions"]
    assert [r["key"] for r in payload["processingReferences"]] == ["chu_2023"]
    assert "@" not in json.dumps(payload)


async def test_legacy_escalation_and_site_funding(server: AmeriFluxServer) -> None:
    payload = await cite(server, sites=["US-Ha1", "ca-let"], include_bibtex=True)
    policy = payload["effectivePolicy"]
    assert policy["code"] == "LEGACY" and "CA-Let" in policy["reason"]
    assert [a["key"] for a in payload["acknowledgments"]] == ["doe_data_portal"]
    assert "data portal" in payload["acknowledgments"][0]["text"]
    assert payload["siteFunding"] == [
        {"siteId": "US-Ha1", "sponsors": ["DOE/TES (AmeriFlux Core site), NSF/LTER"]}
    ]
    assert any("No sponsor in the DOI record of CA-Let" in n for n in payload["notes"])
    let = by_site(payload)["CA-Let"]
    assert let["policy"] == "LEGACY" and let["version"] == "1-5"
    assert let["bibtex"].startswith("@misc{CA_Let_BASE_BADM,")


async def test_fluxnet_product(server: AmeriFluxServer) -> None:
    payload = await cite(server, sites=["US-Ha1", "CA-Let", "AR-Bal"], product="FLUXNET-1F")
    assert payload["product"] == "FLUXNET"
    sites = by_site(payload)
    assert sites["US-Ha1"]["version"] == "v1.3_r1 (1991-2025)"
    assert sites["AR-Bal"]["version"] == "v1.3_r1 (2012-2013)"
    assert payload["missing"] == [
        {
            "siteId": "CA-Let",
            "reason": "CA-Let shares its data under the AmeriFlux Legacy policy; the FLUXNET "
            "product exists only for CC-BY-4.0 sites",
        }
    ]
    assert [a["key"] for a in payload["acknowledgments"]] == [
        "doe_data_service",
        "fluxnet_networks",
    ]
    assert [r["key"] for r in payload["processingReferences"]] == ["pastorello_2020"]
    assert payload["dataAvailability"]["statement"].startswith("The AmeriFlux FLUXNET data were")


async def test_fluxnet2015_constructed_and_tier_two(server: AmeriFluxServer) -> None:
    payload = await cite(server, sites=["US-Ha1", "RU-Sam", "US-xSR"], product="FLUXNET2015")
    sites = by_site(payload)
    assert sites["US-Ha1"]["source"] == "constructed"
    assert sites["US-Ha1"]["citation"].startswith(
        "J. William Munger, Shawn Urbanski, Michael Golden, Carol Barford, Jaclyn Matthes, "
        "Steven Wofsy (1991-2012) FLUXNET2015 US-Ha1"
    )
    assert sites["RU-Sam"]["policy"] == "TIER2"
    assert payload["effectivePolicy"]["code"] == "TIER2"
    texts = " ".join(o["text"] for o in payload["effectivePolicy"]["obligations"])
    assert "in a table" in texts and "three weeks" in texts and "not part of Pastorello" in texts
    assert payload["missing"] == [
        {"siteId": "US-xSR", "reason": "US-xSR is not part of FLUXNET2015"}
    ]
    assert payload["acknowledgments"] == [] and "dataAvailability" not in payload
    assert any("FLUXNET DOI page" in n for n in payload["notes"])


async def test_bif_uses_the_base_doi(server: AmeriFluxServer, router: FixtureRouter) -> None:
    payload = await cite(server, sites=["US-Ha1"], product="BADM")
    assert payload["product"] == "BIF"
    assert by_site(payload)["US-Ha1"]["doi"] == "10.17190/AMF/1246059"
    assert any("no DOI of its own" in n for n in payload["notes"])
    assert payload["dataAvailability"]["statement"].startswith("The AmeriFlux BADM were")
    assert not router.calls_to("/api/v1/DOI/US-Ha1/BIF")
    assert router.calls_to("/api/v1/DOI/US-Ha1/AmeriFlux")


async def test_no_doi_record(server: AmeriFluxServer, router: FixtureRouter) -> None:
    router.add("GET amfcdn.lbl.gov/api/v1/DOI/US-xSR/AmeriFlux", Reply.json({}))
    payload = await cite(server, sites=["US-xSR", "US-Ha1"])
    assert list(by_site(payload)) == ["US-Ha1"]
    assert payload["missing"][0]["reason"].endswith("has no AmeriFlux record for this site")


async def test_datacite_fallback(quick_server: AmeriFluxServer, router: FixtureRouter) -> None:
    router.add("GET amfcdn.lbl.gov/api/v1/DOI/US-Ha1/AmeriFlux", Reply(503, b"busy", "text/plain"))
    payload = await cite(quick_server, sites=["US-Ha1"], include_bibtex=True)
    ha1 = by_site(payload)["US-Ha1"]
    assert ha1["source"] == "datacite" and "version" not in ha1
    assert ha1["citation"].startswith("Munger, J.; Urbanski, Shawn")
    assert (
        "(2016), AmeriFlux US-Ha1 Harvard Forest EMS Tower (HFR1), Harvard University"
        in (ha1["citation"])
    )
    assert ha1["warnings"][0].startswith("versionMissing")
    assert any("DataCite" in n for n in payload["notes"])
    assert payload["source"]["backend"] == "mixed"


async def test_partial_and_total_failure(
    quick_server: AmeriFluxServer, router: FixtureRouter
) -> None:
    router.add("GET amfcdn.lbl.gov/api/v1/DOI/RU-Sam/FLUXNET2015", Reply(503, b"x", "text/plain"))
    partial = await cite(quick_server, sites=["US-Ha1", "RU-Sam"], product="FLUXNET2015")
    assert list(by_site(partial)) == ["US-Ha1"]
    assert "DOI service failed" in partial["missing"][0]["reason"]
    await call_err(
        quick_server,
        "amf_get_citation",
        {"sites": ["RU-Sam"], "product": "FLUXNET2015"},
        "upstream_error",
    )


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ({"sites": ["US-Myb"], "product": "FLUXNET-CH4"}, "feature_unavailable"),
        ({"sites": ["US-Ha1"], "product": "nonsense"}, "invalid_argument"),
        ({"sites": []}, "invalid_argument"),
        ({"sites": ["US-Ha9"]}, "not_found"),
    ],
)
async def test_errors(
    server: AmeriFluxServer, router: FixtureRouter, args: dict[str, Any], code: str
) -> None:
    await call_err(server, "amf_get_citation", args, code)
    assert not router.calls_to("/api/v1/DOI/")
