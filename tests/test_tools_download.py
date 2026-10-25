"""``amf_download_data`` (build step 7): plan, consent, the one POST, ledger and transfers.

The ``data_download`` response is synthetic (its shape comes from AmeriFlux's own
download page script, RESEARCH.md E67; it has not been observed on the wire). Files
are synthetic archives served by :class:`FileServer` on top of the fixture router.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from ameriflux_mcp.ameriflux.client import AmeriFluxClient
from ameriflux_mcp.ameriflux.downloads import DownloadManager, read_sidecar, verify_archive
from ameriflux_mcp.ameriflux.ledger import Ledger, LedgerEntry, canonical_url
from ameriflux_mcp.config import Config
from ameriflux_mcp.context import UpstreamStats
from ameriflux_mcp.errors import ToolError
from ameriflux_mcp.server import AmeriFluxServer
from tests import archives
from tests.fixture_router import Call, FixtureRouter, Reply
from tests.helpers import IDENTITY_ENV, PRIVATE_VALUES, call_ok

POST_KEY = "POST amfcdn.lbl.gov/api/v1/data_download"
FILES = "https://ftp.fluxdata.org/.ameriflux_downloads"
AR_BAL = "AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip"
US_HA1 = "AMF_US-Ha1_BASE-BADM_28-5.zip"
AA_FLX = "AMF_AA-Flx_BIF_CCBY4_20261001.xlsx"
TAG = "?=" + IDENTITY_ENV["AMERIFLUX_USER_ID"]
ETAG = '"5a4e-63f1"'


def zip_bytes(tmp_path: Path, builder: Callable[[Path], Path]) -> bytes:
    directory = tmp_path / "build"
    directory.mkdir(exist_ok=True)
    return builder(directory).read_bytes()


class FileServer:
    """Serves HEAD/GET for files under ``/.ameriflux_downloads/`` and records the POST."""

    def __init__(self, router: FixtureRouter) -> None:
        self.router = router
        self.files: dict[str, bytes] = {}
        self.etags: dict[str, str] = {}
        self.get_overrides: dict[str, Callable[[bytes], Reply]] = {}
        self.posts: list[dict[str, Any]] = []
        self.response: Any = None
        self.post_reply: Reply | None = None
        router.add(POST_KEY, self._post)

    def serve(self, product: str, name: str, content: bytes, etag: str = ETAG) -> str:
        url = f"{FILES}/{product}/{name}"
        self.files[url] = content
        self.etags[url] = etag
        key = url.replace("https://", "")
        self.router.add(f"HEAD {key}", self._head)
        self.router.add(f"GET {key}", self._get)
        return url

    def _post(self, call: Call) -> Reply:
        self.posts.append(json.loads(call.body))
        if self.post_reply is not None:
            return self.post_reply
        return Reply.json(self.response)

    def _head(self, call: Call) -> Reply:
        url = canonical_url(call.url)
        content = self.files[url]
        return Reply(
            200,
            b"",
            "application/zip",
            headers={"content-length": str(len(content)), "etag": self.etags[url]},
        )

    def _get(self, call: Call) -> Reply:
        url = canonical_url(call.url)
        content = self.files[url]
        if url in self.get_overrides:
            return self.get_overrides[url](content)
        return Reply(200, content, "application/zip", headers={"etag": self.etags[url]})

    def gets(self) -> list[Call]:
        return [c for c in self.router.calls if c.method == "GET" and c.host == "ftp.fluxdata.org"]


async def failure(server: AmeriFluxServer, args: dict[str, Any]) -> dict[str, Any]:
    """Call amf_download_data, assert it failed, return the error object."""
    outcome = await server.call("amf_download_data", args)
    assert outcome.is_error, json.dumps(outcome.payload)[:2000]
    error: dict[str, Any] = outcome.payload["error"]
    return error


def link(site: str, url: str, product: str, size: int) -> dict[str, Any]:
    return {"site_id": site, "url": url + TAG, "data_product": product, "download_size": size}


def response(links: list[dict[str, Any]], *, files: list[dict[str, Any]] | None = None) -> Any:
    return {
        "data_urls": links,
        "manifest": {
            "download_timestamp": "2026-10-24 12:00:00",
            "number_of_sites_downloaded": len(links),
            "data_files": files
            or [
                {
                    "site_id": entry["site_id"],
                    "filename": entry["url"].split("/")[-1].split("?")[0],
                    "start_year": "2012",
                    "end_year": "2013",
                    "version": "v1.3_r1",
                    "file_type": entry["data_product"],
                    "timestamp": "2026-10-01",
                    "contact": "pi.person@example.org",
                }
                for entry in links
            ],
        },
        "pi_contact_emails": ["pi.person@example.org", "co.pi@example.org"],
    }


@pytest.fixture
async def client(config: Config, router: FixtureRouter) -> AsyncIterator[AmeriFluxClient]:
    c = AmeriFluxClient(config.upstream, http_transport=router.transport)
    yield c
    await c.aclose()


@pytest.fixture
def files(router: FixtureRouter) -> FileServer:
    return FileServer(router)


@pytest.fixture
def ar_bal(tmp_path: Path, files: FileServer) -> bytes:
    content = zip_bytes(tmp_path, archives.fluxnet_zip)
    url = files.serve("FLUXNET", AR_BAL, content)
    files.response = response([link("AR-Bal", url, "FLUXNET", len(content))])
    return content


def confirm_args(**extra: Any) -> dict[str, Any]:
    return {
        "sites": ["AR-Bal"],
        "product": "FLUXNET",
        "accept_data_policy": "CCBY4.0",
        "confirm": True,
        **extra,
    }


def all_disk_text(root: Path) -> str:
    return "\n".join(p.read_bytes().decode("latin-1") for p in root.rglob("*") if p.is_file())


def assert_private_absent(text: str) -> None:
    for value in PRIVATE_VALUES:
        assert value not in text, value


# ---------------------------------------------------------------------- surface


async def test_tool_is_stdio_only_and_not_idempotent(make_server: Callable[..., Any]) -> None:
    stdio = make_server()
    tool = next(t for t in stdio.tool_definitions() if t.name == "amf_download_data")
    ann = tool.annotations
    assert ann is not None
    assert (ann.read_only_hint, ann.destructive_hint, ann.idempotent_hint, ann.open_world_hint) == (
        False,
        False,
        False,
        True,
    )
    assert "description" not in tool.input_schema["properties"]
    assert "intended_use" not in tool.input_schema["properties"]
    http = make_server(transport="http")
    assert "amf_download_data" not in {t.name for t in http.tool_definitions()}


async def test_kill_switch_removes_the_tool(
    make_server: Callable[..., AmeriFluxServer], config: Config
) -> None:
    cfg = config.model_copy(deep=True)
    cfg.downloads.enabled = False
    server = make_server(config=cfg)
    assert "amf_download_data" not in {t.name for t in server.tool_definitions()}
    error = await failure(server, {"sites": ["AR-Bal"]})
    assert error["code"] == "feature_unavailable"


async def test_identity_cannot_come_from_arguments(make_server: Callable[..., Any]) -> None:
    server = make_server(identity=True)
    for extra in ({"description": "an agent wrote this"}, {"user_email": "x@example.org"}):
        error = await failure(server, {"sites": ["AR-Bal"], **extra})
        assert error["code"] == "invalid_argument"


# ---------------------------------------------------------------------- plan


async def test_plan_shows_the_disclosure_and_sends_nothing(
    make_server: Callable[..., Any], router: FixtureRouter, ar_bal: bytes, files: FileServer
) -> None:
    server = make_server(identity=True)
    out = await call_ok(server, "amf_download_data", {"sites": ["AR-Bal"], "product": "FLUXNET"})
    assert out["mode"] == "plan" and out["ready"] is True and out["blockers"] == []
    disclosure = out["disclosure"]
    assert disclosure["userId"] == disclosure["userEmail"] == "configured (not shown)"
    assert disclosure["userName"] == "configured (not shown)"
    assert disclosure["intendedUse"] == "Research - Other"
    assert disclosure["description"] == (
        "Testing ameriflux-mcp in a sandbox; not a real request. [ameriflux-mcp]"
    )
    assert disclosure["dataProduct"] == "FLUXNET" and disclosure["dataVariant"] == "FULLSET"
    assert disclosure["dataPolicy"] == "CCBY4.0" and disclosure["isTest"] is True
    assert disclosure["siteIds"] == ["AR-Bal"]
    assert any("PIs" in r for r in disclosure["recipients"])
    assert out["eligible"][0]["siteId"] == "AR-Bal" and out["eligible"][0]["years"]
    assert out["policy"]["code"] == "CCBY4.0"
    assert any("FLUXNET" in o["text"] for o in out["policy"]["obligations"])
    assert "accept_data_policy='CCBY4.0', confirm=true" in out["nextSteps"][-1]
    assert files.posts == [] and not [c for c in router.calls if c.method != "GET"]
    assert not [c for c in router.calls if c.host == "ftp.fluxdata.org"]
    assert_private_absent(json.dumps(out))


async def test_plan_without_identity_lists_blockers(
    make_server: Callable[..., Any], files: FileServer
) -> None:
    out = await call_ok(
        make_server(), "amf_download_data", {"sites": ["AR-Bal"], "product": "FLUXNET"}
    )
    assert out["ready"] is False
    assert out["disclosure"]["userId"] == "not configured"
    assert "description" not in out["disclosure"] and "isTest" not in out["disclosure"]
    text = " ".join(out["blockers"])
    assert "identity is incomplete" in text and "IS_TEST" in text
    assert "Do not write the intended use" in out["nextSteps"][0]
    assert files.posts == []


async def test_plan_rules_out_legacy_sites_for_fluxnet(make_server: Callable[..., Any]) -> None:
    out = await call_ok(
        make_server(identity=True),
        "amf_download_data",
        {"sites": ["AR-Bal", "CA-Let"], "product": "FLUXNET"},
    )
    assert [s["siteId"] for s in out["eligible"]] == ["AR-Bal"]
    assert out["ineligible"][0]["siteId"] == "CA-Let"
    assert "Legacy" in out["ineligible"][0]["reason"]


async def test_plan_base_badm_with_a_legacy_site_is_legacy(make_server: Callable[..., Any]) -> None:
    server = make_server(identity=True)
    out = await call_ok(server, "amf_download_data", {"sites": ["US-Ha1", "CA-Let"]})
    assert out["policy"]["code"] == "LEGACY"
    assert {s["siteId"] for s in out["eligible"]} == {"US-Ha1", "CA-Let"}
    assert any("data portal" in o["text"] for o in out["policy"]["obligations"])
    ccby = await call_ok(
        server, "amf_download_data", {"sites": ["US-Ha1", "CA-Let"], "policy": "CC-BY-4.0"}
    )
    assert ccby["policy"]["code"] == "CCBY4.0"
    assert [s["siteId"] for s in ccby["ineligible"]] == ["CA-Let"]


async def test_plan_reports_local_copies(
    make_server: Callable[..., Any], config: Config, tmp_path: Path
) -> None:
    target = config.downloads.directory / "FLUXNET"
    target.mkdir(parents=True)
    archives.fluxnet_zip(target)
    out = await call_ok(
        make_server(identity=True), "amf_download_data", {"sites": ["AR-Bal"], "product": "FLUXNET"}
    )
    assert out["localCopies"][0]["siteId"] == "AR-Bal"
    assert out["localCopies"][0]["version"] == "v1.3_r1"
    assert any("still notifies the PIs" in n for n in out["notes"])


# ---------------------------------------------------------------------- refusals before any POST


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        ({"accept_data_policy": None}, "policy_not_accepted"),
        ({"accept_data_policy": "LEGACY"}, "policy_mismatch"),
    ],
)
async def test_confirm_needs_the_accepted_policy(
    make_server: Callable[..., Any], files: FileServer, args: dict[str, Any], reason: str
) -> None:
    error = await failure(make_server(identity=True), confirm_args(**args))
    assert error["code"] == "invalid_argument" and error["details"]["reason"] == reason
    assert files.posts == []


async def test_fluxnet_legacy_fails_before_any_request(
    make_server: Callable[..., Any], router: FixtureRouter
) -> None:
    error = await failure(
        make_server(identity=True),
        confirm_args(policy="LEGACY", accept_data_policy="LEGACY"),
    )
    assert error["details"]["reason"] == "fluxnet_requires_ccby"
    assert router.calls == []


@pytest.mark.parametrize("product", ["FLUXNET2015", "FLUXNET-CH4"])
async def test_fluxnet2015_is_not_downloaded(
    make_server: Callable[..., Any], router: FixtureRouter, product: str
) -> None:
    error = await failure(make_server(identity=True), {"sites": ["US-Ha1"], "product": product})
    assert error["code"] == "feature_unavailable"
    assert error["details"]["guide"] == "ameriflux://guide/fluxnet2015-access"
    assert router.calls == []


async def test_confirm_without_identity_is_auth_required(
    make_server: Callable[..., Any], files: FileServer
) -> None:
    error = await failure(make_server(), confirm_args())
    assert error["code"] == "auth_required"
    assert error["details"]["reason"] == "identity_missing"
    assert error["details"]["guide"] == "ameriflux://guide/identity"
    assert files.posts == []


async def test_is_test_unset_is_auth_required(
    make_server: Callable[..., Any], identity_config: Config, files: FileServer
) -> None:
    cfg = identity_config.model_copy(deep=True)
    cfg.identity.is_test = None
    error = await failure(make_server(config=cfg), confirm_args())
    assert error["code"] == "auth_required" and error["details"]["reason"] == "is_test_unset"
    assert files.posts == []


@pytest.mark.parametrize(
    ("profile", "reason"), [("thesis", "profile_missing"), ("default", "profile_incomplete")]
)
async def test_profile_problems_are_auth_required(
    make_server: Callable[..., Any],
    identity_config: Config,
    files: FileServer,
    profile: str,
    reason: str,
) -> None:
    cfg = identity_config.model_copy(deep=True)
    cfg.identity.profiles["default"].description = None
    error = await failure(make_server(config=cfg), confirm_args(profile=profile))
    assert error["code"] == "auth_required" and error["details"]["reason"] == reason
    assert files.posts == []


async def test_no_eligible_site_sends_nothing(
    make_server: Callable[..., Any], files: FileServer
) -> None:
    error = await failure(make_server(identity=True), confirm_args(sites=["CA-Let"]))
    assert error["code"] == "not_found" and error["details"]["reason"] == "no_eligible_sites"
    assert files.posts == []


# ---------------------------------------------------------------------- a confirmed download


async def test_confirmed_download_writes_verified_files(
    make_server: Callable[..., Any],
    router: FixtureRouter,
    config: Config,
    files: FileServer,
    ar_bal: bytes,
) -> None:
    out = await call_ok(make_server(identity=True), "amf_download_data", confirm_args())
    assert out["mode"] == "download"
    # The one POST: the configured identity, the tagged description, a JSON boolean.
    assert len(files.posts) == 1
    body = files.posts[0]
    assert body == {
        "user_id": "fluxtester42",
        "user_email": "flux.tester@example.org",
        "user_name": "Flux Tester",
        "site_ids": ["AR-Bal"],
        "data_product": "FLUXNET",
        "data_variant": "FULLSET",
        "data_policy": "CCBY4.0",
        "intended_use": "Research - Other",
        "description": "Testing ameriflux-mcp in a sandbox; not a real request. [ameriflux-mcp]",
        "is_test": True,
    }
    # The file server never sees the ?=<user_id> tag (the router fails on identity leaks).
    assert [c.url for c in files.gets()] == [f"{FILES}/FLUXNET/{AR_BAL}"]
    assert files.gets()[0].headers["if-match"] == ETAG
    assert files.gets()[0].headers["accept-encoding"] == "identity"
    (entry,) = out["files"]
    path = config.downloads.directory / "FLUXNET" / AR_BAL
    assert entry["status"] == "downloaded" and entry["path"] == str(path)
    assert entry["sha256"] == hashlib.sha256(ar_bal).hexdigest()
    assert entry["bytes"] == len(ar_bal) and entry["version"] == "v1.3_r1"
    assert path.read_bytes() == ar_bal
    sidecar = read_sidecar(path)
    assert sidecar is not None
    assert sidecar["sha256"] == entry["sha256"] and sidecar["etag"] == ETAG
    assert sidecar["url"] == f"{FILES}/FLUXNET/{AR_BAL}" and sidecar["isTest"] is True
    assert sidecar["citation"]["doi"].startswith("10.17190/AMF/")
    assert out["citations"][0]["siteId"] == "AR-Bal"
    # Manifest: written next to the files, upstream rows without emails.
    manifest = Path(out["manifest"]["path"])
    assert manifest.parent == config.downloads.directory / "manifests"
    assert out["manifest"]["dataFiles"][0]["filename"] == AR_BAL
    assert out["piContactCount"] == 2
    assert out["totals"]["files"] == 1
    assert not list(config.downloads.directory.rglob("*.part"))
    # Nothing on disk or in the result carries the identity or an email.
    disk = all_disk_text(config.downloads.directory)
    assert_private_absent(disk)
    written = "\n".join(p.read_text() for p in config.downloads.directory.rglob("*.json"))
    assert "@" not in written
    assert_private_absent(json.dumps(out))
    assert "pi.person" not in json.dumps(out)
    # The file reads with the local tools.
    preview = await call_ok(
        make_server(identity=True),
        "amf_preview_data",
        {"file": entry["path"], "resolution": "DD"},
    )
    assert preview["fileInfo"]["stepMinutes"] == 1440


async def test_rerun_keeps_existing_files(
    make_server: Callable[..., Any], files: FileServer, ar_bal: bytes
) -> None:
    server = make_server(identity=True)
    await call_ok(server, "amf_download_data", confirm_args())
    again = await call_ok(server, "amf_download_data", confirm_args())
    assert len(files.posts) == 2  # each confirmed call is a new, logged request
    assert len(files.gets()) == 1
    (entry,) = again["files"]
    assert entry["status"] == "skipped" and entry["reason"] == "exists"
    assert entry["identical"] is True


async def test_replace_refetches_a_different_file(
    make_server: Callable[..., Any], config: Config, files: FileServer, ar_bal: bytes
) -> None:
    path = config.downloads.directory / "FLUXNET" / AR_BAL
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")
    server = make_server(identity=True)
    kept = await call_ok(server, "amf_download_data", confirm_args())
    assert kept["files"][0]["identical"] is False and path.read_bytes() == b"old"
    assert any("if_exists='replace'" in n for n in kept["notes"])
    replaced = await call_ok(server, "amf_download_data", confirm_args(if_exists="replace"))
    assert replaced["files"][0]["status"] == "downloaded" and path.read_bytes() == ar_bal


async def test_bif_goes_as_base_badm_and_skips_fluxnet_bif(
    make_server: Callable[..., Any], config: Config, files: FileServer
) -> None:
    rows = archives.bif_rows("US-CRT")
    content = archives.xlsx_bytes(rows)
    url = files.serve("BIF", AA_FLX, content)
    other = f"{FILES}/FLUXNET-BIF/AMF_AA-Flx_FLUXNET-BIF_CCBY4_20261001.xlsx"
    files.response = response(
        [link("AA-Flx", url, "BIF", len(content)), link("AA-Flx", other, "FLUXNET-BIF", 10)]
    )
    out = await call_ok(
        make_server(identity=True),
        "amf_download_data",
        {"sites": ["aa-flx"], "product": "BIF", "accept_data_policy": "CCBY4.0", "confirm": True},
    )
    assert files.posts[0]["data_product"] == "BASE-BADM"
    assert files.posts[0]["site_ids"] == ["AA-Flx"]
    assert "data_variant" not in files.posts[0]
    assert out["dataProduct"] == "BASE-BADM"
    assert [f["name"] for f in out["files"]] == [AA_FLX]
    assert out["files"][0]["status"] == "downloaded"
    assert out["skipped"][0]["reason"] == "fluxnet_bif"
    assert (config.downloads.directory / "BIF" / AA_FLX).exists()
    assert out["citations"] == []


async def test_bif_needs_a_bulk_site(make_server: Callable[..., Any]) -> None:
    error = await failure(make_server(identity=True), {"sites": ["US-Ha1"], "product": "BIF"})
    assert error["details"]["reason"] == "bif_needs_bulk_site"


async def test_links_off_the_allow_list_are_never_fetched(
    make_server: Callable[..., Any], files: FileServer, ar_bal: bytes
) -> None:
    bad = [
        link(
            "AR-Bal",
            "https://ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/x.zip",
            "FLUXNET",
            1,
        ),
        link("AR-Bal", "https://evil.example.org/AMF_AR-Bal.zip", "FLUXNET", 1),
        link("AR-Bal", "https://api.datacite.org/dois/AMF_AR-Bal.zip", "FLUXNET", 1),
        link("AR-Bal", f"{FILES}/FLUXNET/..%2F..%2Fescape.zip", "FLUXNET", 1),
        link("US-Ha1", f"{FILES}/FLUXNET/{US_HA1}", "FLUXNET", 1),
    ]
    files.response["data_urls"].extend(bad)
    out = await call_ok(make_server(identity=True), "amf_download_data", confirm_args())
    reasons = [s["reason"] for s in out["skipped"]]
    assert reasons == [
        "off_allow_list",
        "off_allow_list",
        "off_allow_list",
        "unsafe_name",
        "not_requested",
    ]
    assert [c.url for c in files.gets()] == [f"{FILES}/FLUXNET/{AR_BAL}"]


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        (
            lambda c: Reply(200, c[:-10], "application/zip", headers={"etag": ETAG}),
            "head_get_mismatch",
        ),
        (
            lambda c: Reply(200, c, "application/zip", headers={"etag": '"other"'}),
            "head_get_mismatch",
        ),
        (lambda c: Reply(412, b"", "text/plain"), "etag_changed"),
        (
            lambda c: Reply(
                200,
                c[:200] + bytes([c[200] ^ 0xFF]) + c[201:],
                "application/zip",
                headers={"etag": ETAG},
            ),
            "bad_crc",
        ),
    ],
)
async def test_integrity_failures_keep_nothing(
    make_server: Callable[..., Any],
    config: Config,
    files: FileServer,
    ar_bal: bytes,
    override: Callable[[bytes], Reply],
    reason: str,
) -> None:
    files.get_overrides[f"{FILES}/FLUXNET/{AR_BAL}"] = override
    out = await call_ok(make_server(identity=True), "amf_download_data", confirm_args())
    (entry,) = out["files"]
    assert entry["status"] == "failed" and entry["reason"] in (reason, "bad_archive")
    assert entry["error"].startswith("checksum_mismatch")
    assert not (config.downloads.directory / "FLUXNET" / AR_BAL).exists()
    assert not list(config.downloads.directory.rglob("*.part"))


async def test_per_file_and_per_call_limits(
    make_server: Callable[..., Any], identity_config: Config, files: FileServer, ar_bal: bytes
) -> None:
    cfg = identity_config.model_copy(deep=True)
    cfg.downloads.max_file_bytes = 100
    out = await call_ok(make_server(config=cfg), "amf_download_data", confirm_args())
    assert out["files"][0]["reason"] == "over_file_limit"
    cfg.downloads.max_file_bytes = 10**9
    cfg.downloads.max_bytes_per_call = 100
    out = await call_ok(make_server(config=cfg), "amf_download_data", confirm_args())
    assert out["files"][0]["status"] == "skipped" and out["files"][0]["reason"] == "call_byte_limit"
    assert files.gets() == []


async def test_post_errors_map_without_retry(
    make_server: Callable[..., Any], files: FileServer, ar_bal: bytes
) -> None:
    server = make_server(identity=True)
    files.post_reply = Reply(403, b'{"message":"Forbidden fluxtester42"}')
    error = await failure(server, confirm_args())
    assert error["code"] == "upstream_forbidden"
    assert_private_absent(json.dumps(error))
    files.post_reply = Reply(500, b"boom")
    error = await failure(server, confirm_args())
    assert error["code"] == "upstream_error"
    assert len(files.posts) == 2  # a 5xx after sending is not retried
    files.post_reply = None
    files.response = {"urls": []}
    error = await failure(server, confirm_args())
    assert error["code"] == "upstream_error" and error["details"]["drift"]["missing"] == [
        "data_urls"
    ]


async def test_empty_response_is_reported(
    make_server: Callable[..., Any], files: FileServer
) -> None:
    files.response = {"data_urls": [], "manifest": {}, "pi_contact_emails": []}
    out = await call_ok(make_server(identity=True), "amf_download_data", confirm_args())
    assert out["files"] == [] and any("returned no files" in n for n in out["notes"])


# ---------------------------------------------------------------------- units


def _entry(url: str = f"{FILES}/FLUXNET/{AR_BAL}") -> LedgerEntry:
    return LedgerEntry(
        url=url,
        name=url.rsplit("/", 1)[-1],
        site_id="AR-Bal",
        data_product="FLUXNET",
        product="FLUXNET",
        policy="CCBY4.0",
        request_id="r1",
    )


def test_ledger_strips_the_tag_and_gates_urls(client: AmeriFluxClient) -> None:
    ledger = Ledger()
    kept, skipped = ledger.record(
        [{"site_id": "AR-Bal", "url": f"{FILES}/FLUXNET/{AR_BAL}{TAG}", "download_size": "12"}],
        request_id="r1",
        product="FLUXNET",
        policy="CCBY4.0",
        requested_sites=["AR-Bal"],
        check=client.check_download_link,
    )
    assert skipped == [] and kept[0].url == f"{FILES}/FLUXNET/{AR_BAL}"
    assert kept[0].download_size == 12
    assert "fluxtester42" not in repr(kept)
    assert ledger.require(f"{FILES}/FLUXNET/{AR_BAL}?=anything") is kept[0]
    with pytest.raises(ToolError) as exc:
        ledger.require(f"{FILES}/FLUXNET/AMF_US-Ha1_FLUXNET_1991-2025_v1.3_r1.zip")
    assert exc.value.code == "download_denied"
    assert exc.value.details["reason"] == "not_in_ledger"


async def test_manager_refuses_urls_outside_the_ledger(
    client: AmeriFluxClient, config: Config, router: FixtureRouter
) -> None:
    manager = DownloadManager(config.downloads, client, zip_member_max_bytes=10**6)
    with pytest.raises(ToolError) as exc:
        await manager.head(_entry(), stats=UpstreamStats())
    assert exc.value.code == "download_denied"
    assert router.calls == []


def test_destination_refuses_escapes(client: AmeriFluxClient, config: Config) -> None:
    manager = DownloadManager(config.downloads, client, zip_member_max_bytes=10**6)
    for name in ("..", ".hidden.zip", "a/b.zip"):
        bad = LedgerEntry(
            url=f"{FILES}/x/{name}",
            name=name,
            site_id="AR-Bal",
            data_product="FLUXNET",
            product="FLUXNET",
            policy="CCBY4.0",
            request_id="r1",
        )
        with pytest.raises(ToolError):
            manager.destination(bad)


def test_verify_archive_reports_refused_members(tmp_path: Path) -> None:
    hostile = archives.hostile_zip(tmp_path)
    notes = verify_archive(hostile, max_member_bytes=10**9)
    assert notes and all("refused" in n for n in notes)
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK\x03\x04 not a zip")
    with pytest.raises(ToolError) as exc:
        verify_archive(broken, max_member_bytes=10**9)
    assert exc.value.code == "checksum_mismatch"
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("a.csv", "x\n")
    assert verify_archive(good, max_member_bytes=10**9) == []


def test_the_one_post_has_one_caller() -> None:
    """Static guard (D11): one ``.post(`` in the package, called from the download tool only."""
    src = Path(__file__).resolve().parents[1] / "src" / "ameriflux_mcp"
    posts: list[str] = []
    callers: list[str] = []
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(src))
        posts += [
            rel for line in text.splitlines() if "._http.post(" in line or "httpx.post(" in line
        ]
        callers += [
            rel for line in text.splitlines() if "post_download(" in line and "def " not in line
        ]
    assert posts == ["ameriflux/client.py"]
    assert callers == ["tools/download.py"]
