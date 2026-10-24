"""Citation building, DataCite parsing, and the measurement-height and coverage parsers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ameriflux_mcp.ameriflux.catalog import SiteRecord, TierYears
from ameriflux_mcp.ameriflux.citation import (
    VERSION_MISSING,
    SiteCitation,
    bibtex,
    fluxnet2015_text,
    from_doi_record,
    parse_datacite,
    parse_doi,
)
from ameriflux_mcp.ameriflux.client import Fetched
from ameriflux_mcp.ameriflux.variables import coverage, heights
from ameriflux_mcp.errors import AmeriFluxApiError
from tests.fixture_router import FIXTURES, load_manifest

MANIFEST = load_manifest()


def fixture(key: str) -> bytes:
    return (FIXTURES / MANIFEST[key]["file"]).read_bytes()


def doi_payload(site: str, segment: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(fixture(f"GET amfcdn.lbl.gov/api/v1/DOI/{site}/{segment}"))
    return data


def fetched(body: bytes, endpoint: str = "GET example/x") -> Fetched:
    return Fetched(body=body, status=200, content_type=None, endpoint=endpoint)


HA1 = SiteRecord(
    site_id="US-Ha1",
    name="Harvard Forest EMS Tower (HFR1)",
    collections=frozenset({"ameriflux", "fluxnet2015"}),
    policy="CCBY4.0",
    fluxnet2015=TierYears(ccby="1991-2012", tier2="1991-2012"),
)


def test_parse_doi_record() -> None:
    record = parse_doi(doi_payload("US-Ha1", "AmeriFlux"))
    assert record.doi == "10.17190/AMF/1246059" and record.policy == "CCBY4.0"
    assert [c.name for c in record.authors][:2] == ["J. William Munger", "Shawn Urbanski"]
    assert all(c.role == "Author" for c in record.authors)
    assert len(record.contributors) > len(record.authors)  # the "Other" role is not an author
    assert record.sponsors == ("DOE/TES (AmeriFlux Core site), NSF/LTER",)
    assert record.references and record.references[0].doi
    assert record.site_page == "https://ameriflux.lbl.gov/sites/siteinfo/US-Ha1"
    legacy = parse_doi(doi_payload("CA-Let", "AmeriFlux"))
    assert legacy.policy == "LEGACY" and legacy.sponsors == ()


@pytest.mark.parametrize(
    ("segment", "version", "year"),
    [("AmeriFlux", "28-5", "2026"), ("FLUXNET", "v1.3_r1 (1991-2025)", "2026")],
)
def test_versioned_citations(segment: str, version: str, year: str) -> None:
    product = "BASE-BADM" if segment == "AmeriFlux" else "FLUXNET"
    citation = from_doi_record(HA1, product, parse_doi(doi_payload("US-Ha1", segment)))
    assert citation.source == "amfcdn" and citation.version == version and citation.year == year
    assert f"Ver. {version}," in citation.text and citation.text.endswith(citation.doi)


def test_fluxnet2015_is_constructed() -> None:
    doi = parse_doi(doi_payload("US-Ha1", "FLUXNET2015"))
    assert doi.citation is None
    text = fluxnet2015_text(HA1, doi)
    assert text == (
        "J. William Munger, Shawn Urbanski, Michael Golden, Carol Barford, Jaclyn Matthes, "
        "Steven Wofsy (1991-2012) FLUXNET2015 US-Ha1 Harvard Forest EMS Tower (HFR1), Dataset. "
        "https://doi.org/10.18140/FLX/1440071"
    )
    citation = from_doi_record(HA1, "FLUXNET2015", doi)
    assert citation.source == "constructed" and citation.version is None


def test_bibtex() -> None:
    citation = from_doi_record(HA1, "BASE-BADM", parse_doi(doi_payload("US-Ha1", "AmeriFlux")))
    entry = bibtex(citation)
    assert entry.startswith("@misc{US_Ha1_BASE_BADM,")
    assert "author = {Munger, J. William and Urbanski, Shawn" in entry
    assert "version = {28-5}" in entry and "doi = {10.17190/AMF/1246059}" in entry
    org = SiteCitation(
        site_id="US-xSR",
        product="FLUXNET2015",
        doi="10.1/x",
        text="t",
        source="datacite",
        bibtex_authors=["NEON (National Ecological Observatory Network)"],
    )
    assert "author = {{NEON (National Ecological Observatory Network)}}" in bibtex(org)
    assert "publisher" not in bibtex(org)


def test_parse_datacite() -> None:
    meta = parse_datacite(fetched(fixture("GET api.datacite.org/dois/10.17190/AMF/1246059")))
    assert meta["version"] is None and meta["year"] == "2016"
    assert meta["publisher"] == "Harvard University" and meta["creators"][0].startswith("Munger")
    with pytest.raises(AmeriFluxApiError) as exc:
        parse_datacite(fetched(b"{}"))
    assert exc.value.kind == "decode"
    assert "versionMissing" in VERSION_MISSING


def test_heights_parsers() -> None:
    page = fixture("GET ameriflux.lbl.gov/data/measurement-height/")
    link = heights.parse_page(fetched(page))
    assert link["date"] == "2026-09-08" and link["url"].endswith("_20260908.csv")
    key = (
        "GET ftp.fluxdata.org/.ameriflux_downloads/measurement_height/"
        "BASE_MeasurementHeight_20260908.csv"
    )
    rows = heights.parse_csv(fetched(fixture(key)))
    assert set(rows) == {"AR-Bal", "CA-Let", "US-CRT", "US-Ha1"}
    ta = [r for r in rows["US-Ha1"] if r[0] == "TA_1_1_1"]
    assert ta and ta[0][1] == 27.9 and ta[0][2] == "TEMP-Thermis"
    with pytest.raises(AmeriFluxApiError) as no_link:
        heights.parse_page(fetched(b"<html>moved</html>"))
    assert no_link.value.kind == "drift"
    with pytest.raises(AmeriFluxApiError) as columns:
        heights.parse_csv(fetched(b"Site,Var\nUS-Ha1,TA\n"))
    assert columns.value.kind == "drift" and "Height" in columns.value.missing


def test_coverage_parser() -> None:
    key = (
        "GET raw.githubusercontent.com/chuhousen/amerifluxr/master/data-summary/"
        "AMF_AA-Flx_BASE_VARIABLE-AVAILABILITY_LATEST.csv"
    )
    data = coverage.parse_csv(fetched(fixture(key)))
    assert data["created"] == "2025-10-20" and set(data["sites"]) == {"US-CRT", "US-Ha1"}
    cov = coverage.Coverage(created=data["created"], raw=data["sites"])
    rows = {r.variable: r for r in cov.site_rows("US-Ha1")}
    ta = rows["TA_1_1_1"]
    assert (
        not ta.gap_filled and min(ta.years) == 1991 and all(0 < f <= 1 for f in ta.years.values())
    )
    assert cov.site_rows("XX-Zzz") == []
    with pytest.raises(AmeriFluxApiError):
        coverage.parse_csv(fetched(b"create_date:2025-10-20\nSITE_ID,VARIABLE\n"))
