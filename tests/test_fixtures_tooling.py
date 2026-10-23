"""scripts/record_fixtures.py rules and the FixtureRouter's refusals."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from tests.fixture_router import FIXTURE_SITES, FixtureRouter
from tests.helpers import PRIVATE_VALUES

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "record_fixtures.py"


@pytest.fixture(scope="module")
def rec() -> ModuleType:
    spec = importlib.util.spec_from_file_location("record_fixtures", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_fixtures_pass_check(rec: ModuleType) -> None:
    assert rec.check() == []


def test_scenarios_are_allow_listed_gets(rec: ModuleType) -> None:
    for path, query in rec.SCENARIOS:
        url = httpx.URL(f"{rec.API}/{path}", params=query or None)
        from tests.fixture_router import canonical_key

        assert rec._allowed(canonical_key("GET", url)), path
    assert not rec._allowed("POST amfcdn.lbl.gov/api/v1/data_download")
    assert not rec._allowed("GET ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/x.zip")
    assert not rec._allowed("GET example.org/api/v1/fp_var")


def _write(directory: Path, manifest: list[dict[str, object]], files: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    for name, text in files.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(text)


def test_check_rules(rec: ModuleType, tmp_path: Path) -> None:
    key = "GET amfcdn.lbl.gov/api/v1/fp_var?limits=True"
    _write(
        tmp_path,
        [
            {"key": key, "status": 200, "file": "v1/a.json"},
            {"key": "GET amfcdn.lbl.gov/api/v1/x", "status": 200, "file": "v1/missing.json"},
            {"key": "POST amfcdn.lbl.gov/api/v1/data_download", "status": 200},
        ],
        {
            "v1/a.json": '{"pi": "someone@example.edu", "ok": "fine@example.org"}',
            "v1/stray.json": "x" * (41 * 1024),
        },
    )
    problems = "\n".join(rec.check(tmp_path))
    assert "v1/missing.json is missing" in problems
    assert "not an allow-listed GET: POST" in problems
    assert "v1/a.json: an email outside example.org" in problems
    assert "v1/stray.json: 41984 bytes > 40960" in problems
    assert "v1/stray.json: not referenced" in problems
    assert rec.check(tmp_path / "nowhere") == ["manifest.json: missing"]


def test_email_rewrite_is_stable(rec: ModuleType) -> None:
    text = "a: Jane.Doe@Example.EDU, b: jane.doe@example.edu, c: other@example.net"
    out = rec.scrub_emails(text)
    found = re.findall(r"[\w.+-]+@[\w.-]+", out)
    assert all(e.endswith("@example.org") for e in found)
    assert found[0] == found[1] != found[2]


def test_transforms_filter_to_fixture_sites(rec: ModuleType) -> None:
    sites = sorted(FIXTURE_SITES)
    info = {
        "values": [
            {"site_id": "US-Ha1", "site_desc": "x" * 500},
            {"site_id": "ZZ-Out", "site_desc": "y"},
        ]
    }
    kept, note = rec.transform("v2/site_info_display/AmeriFlux", info)
    assert [r["site_id"] for r in kept["values"]] == ["US-Ha1"]
    assert len(kept["values"][0]["site_desc"]) == rec.DESC_CHARS + 1 and note
    rows = [{"SITE_ID": sites[0]}, {"SITE_ID": "ZZ-Out"}]
    assert rec.transform("v1/data_availability/A/B/C", rows)[0] == [{"SITE_ID": sites[0]}]
    tree = {"AmeriFlux": {"BIF": {"CCBY4.0": [["US-Ha1", "x"], ["ZZ-Out", "y"]]}}}
    assert rec.transform("v1/site_availability", tree)[0] == {
        "AmeriFlux": {"BIF": {"CCBY4.0": [["US-Ha1", "x"]]}}
    }
    doi = {"REFERENCES": list(range(10))}
    assert len(rec.transform("v1/DOI/US-Ha1/AmeriFlux", doi)[0]["REFERENCES"]) == 4
    assert rec.transform("v1/fp_var", [1]) == ([1], None)


def test_fixture_names(rec: ModuleType) -> None:
    name = rec.fixture_name("GET amfcdn.lbl.gov/api/v1/DOI/US-Ha1/FLUXNET", 200)
    assert re.fullmatch(r"v1/DOI_US_Ha1_FLUXNET_200_[0-9a-f]{8}\.json", name)


# ---------------------------------------------------------------------- router


def _get(router: FixtureRouter, url: str, **kw: object) -> httpx.Response:
    with httpx.Client(transport=router.transport) as client:
        return client.request(kw.pop("method", "GET"), url, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "https://ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/FLX_US-Ha1.zip",
        "https://example.org/api/v1/fp_var",
        "https://ameriflux.lbl.gov/data/data-download-log/",
    ],
)
def test_router_refuses_off_list_requests(url: str) -> None:
    router = FixtureRouter()
    with pytest.raises(AssertionError):
        _get(router, url)
    assert router.unexpected


def test_router_refuses_unrecorded_and_posts() -> None:
    router = FixtureRouter()
    with pytest.raises(AssertionError, match="unexpected upstream call"):
        _get(router, "https://amfcdn.lbl.gov/api/v1/not_recorded")
    with pytest.raises(AssertionError, match="POST without a fixture"):
        _get(router, "https://amfcdn.lbl.gov/api/v1/data_download", method="POST", json={})


@pytest.mark.parametrize("value", PRIVATE_VALUES)
def test_router_refuses_identity_upstream(value: str) -> None:
    router = FixtureRouter()
    with pytest.raises(AssertionError, match="identity sent"):
        _get(router, "https://amfcdn.lbl.gov/api/v1/fp_var", params={"limits": "True", "u": value})
    with pytest.raises(AssertionError, match="identity sent"):
        _get(router, "https://amfcdn.lbl.gov/api/v1/fp_var", headers={"X-Who": value})


def test_router_replays_fixtures() -> None:
    response = _get(FixtureRouter(), "https://amfcdn.lbl.gov/api/v1/fp_var?limits=True")
    assert response.status_code == 200 and len(response.json()) == 145
