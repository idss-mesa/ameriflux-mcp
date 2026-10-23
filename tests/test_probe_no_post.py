"""scripts/probe_api.py must never write upstream (DESIGN.md D28).

AmeriFlux logs every ``data_download`` request and sends the requester's identity and
intended use to the site PIs, so a probe that POSTs, even by mistake, discloses
something on the user's behalf. These checks are static (the source names no write
method and passes no request body) and dynamic (the guard refuses before any socket).
"""

from __future__ import annotations

import ast
import importlib.util
import re
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_api.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("probe_api", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = _load()

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("the probe opened a connection")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    return module


def test_source_never_names_post() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    hits = [
        n for n, line in enumerate(source.splitlines(), 1) if re.search(r"\bpost\b", line, re.I)
    ]
    assert not hits, f"probe_api.py names POST on line(s) {hits}"


def test_no_request_body_anywhere() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        assert all(kw.arg != "data" for kw in node.keywords), (
            f"line {node.lineno}: a call passes data="
        )
        name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if name == "Request":
            assert len(node.args) == 1, f"line {node.lineno}: Request() given a positional body"
        if name == "urlopen":
            assert len(node.args) == 1, f"line {node.lineno}: urlopen() given a positional body"


def test_allowed_methods_are_read_only(probe: ModuleType) -> None:
    assert frozenset({"GET", "HEAD"}) == probe.ALLOWED_METHODS


@pytest.mark.parametrize("method", ["POST", "post", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_write_methods_refused_before_any_socket(probe: ModuleType, method: str) -> None:
    with pytest.raises(probe.ProbeRefused):
        probe.http(method, "https://amfcdn.lbl.gov/api/v1/data_download")


@pytest.mark.parametrize(
    "url",
    [
        "http://amfcdn.lbl.gov/api/v1/fp_var",
        "https://example.org/api/v1/fp_var",
        "https://amfcdn.lbl.gov/create",
        "https://ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/FLX_US-Ha1.zip",
        "https://ftp.fluxdata.org/.fluxnet_downloads_67934/webdoc/../paper_test/x.zip",
        "https://ftp.fluxdata.org/.ameriflux_downloads/FLUXNET/AMF_US-Ha1_FLUXNET.zip",
        "https://ftp.fluxdata.org/.ameriflux_downloads/BASE-BADM/AMF_US-Ha1_BASE-BADM_28-5.zip",
        "https://ameriflux.lbl.gov/data/data-download-log/",
        "https://fluxnet.org/data/download-historical-data/",
    ],
)
def test_hosts_and_paths_outside_allow_list_refused(probe: ModuleType, url: str) -> None:
    with pytest.raises(probe.ProbeRefused):
        probe.http("GET", url)


def test_allow_list_admits_the_discovery_api(probe: ModuleType) -> None:
    probe.check_request("GET", "https://amfcdn.lbl.gov/api/v2/site_info_display/AmeriFlux")
    probe.check_request(
        "HEAD",
        "https://ftp.fluxdata.org/.ameriflux_downloads/measurement_height/"
        "BASE_MeasurementHeight_20260908.csv",
    )


def test_scrub_removes_emails(probe: ModuleType) -> None:
    text = '{"team_member_email": "j.doe+flux@example.edu", "pi": "A B <a_b@example.org>"}'
    scrubbed = probe.scrub(text)
    assert "@" not in scrubbed
    assert scrubbed.count("<email>") == 2


def test_selftest_passes(probe: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert probe.selftest() == 0
    assert "selftest ok" in capsys.readouterr().out
