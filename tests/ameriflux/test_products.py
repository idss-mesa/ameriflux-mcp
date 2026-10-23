from __future__ import annotations

import pytest

from ameriflux_mcp.ameriflux.products import (
    MATRIX,
    availability_path,
    download_request,
    normalize_policy,
    normalize_product,
    validate,
)
from ameriflux_mcp.ameriflux.siteid import RENAMES, is_site_id, rename_note, renamed
from ameriflux_mcp.errors import ToolError


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BASE-BADM", "BASE-BADM"),
        ("base", "BASE-BADM"),
        ("AmeriFlux BASE", "BASE-BADM"),
        ("BADM", "BIF"),
        ("bif", "BIF"),
        ("FLUXNET", "FLUXNET"),
        ("FLUXNET-1F", "FLUXNET"),
        ("oneflux", "FLUXNET"),
        ("fluxnet 2015", "FLUXNET2015"),
        ("FLUXNET_2015", "FLUXNET2015"),
        ("FLUXNET-CH4", "FLUXNET-CH4"),
        ("ch4", "FLUXNET-CH4"),
    ],
)
def test_normalize_product(text: str, expected: str) -> None:
    assert normalize_product(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CCBY4.0", "CCBY4.0"),
        ("CC-BY-4.0", "CCBY4.0"),
        ("cc by 4.0", "CCBY4.0"),
        ("ccby4", "CCBY4.0"),
        ("Tier 1", "CCBY4.0"),
        ("Legacy", "LEGACY"),
        ("AmeriFlux Legacy", "LEGACY"),
        ("Tier2", "TIER2"),
        ("tier two", "TIER2"),
    ],
)
def test_normalize_policy(text: str, expected: str) -> None:
    assert normalize_policy(text) == expected


@pytest.mark.parametrize("bad", ["", "FOO", "BASE-BAD", "tier3"])
def test_unknown_values_are_invalid_arguments(bad: str) -> None:
    for fn in (normalize_product, normalize_policy):
        with pytest.raises(ToolError) as exc:
            fn(bad)
        assert exc.value.code == "invalid_argument" and exc.value.details["valid"]


def test_matrix_matches_research() -> None:
    assert {p: m.policies for p, m in MATRIX.items()} == {
        "BASE-BADM": ("CCBY4.0", "LEGACY"),
        "BIF": ("CCBY4.0", "LEGACY"),
        "FLUXNET": ("CCBY4.0",),
        "FLUXNET2015": ("CCBY4.0", "TIER2"),
        "FLUXNET-CH4": ("CCBY4.0", "TIER2"),
    }
    assert MATRIX["BIF"].doi_segment == "AmeriFlux"  # BADM is cited with the BASE DOI (D9)


def test_invalid_combinations() -> None:
    with pytest.raises(ToolError) as tier2:
        validate("BASE-BADM", "TIER2")
    assert tier2.value.details["reason"] == "invalid_combination"
    with pytest.raises(ToolError) as legacy:
        validate("FLUXNET", "LEGACY")
    assert legacy.value.details["reason"] == "fluxnet_requires_ccby"
    with pytest.raises(ToolError):
        validate("FLUXNET2015", "LEGACY")


def test_availability_paths() -> None:
    assert (
        availability_path("BASE-BADM", "LEGACY")
        == "v1/data_availability/AmeriFlux/BASE-BADM/LEGACY"
    )
    assert (
        availability_path("FLUXNET2015", "TIER2")
        == "v1/data_availability/FLUXNET/FLUXNET2015/TIER2"
    )
    assert availability_path("BIF", "CCBY4.0") is None  # site_availability only (D7)
    with pytest.raises(ToolError):
        availability_path("FLUXNET", "LEGACY")


def test_download_request_mapping() -> None:
    bif = download_request("BIF", ["AA-Flx"])
    assert (bif.data_product, bif.site_ids, bif.data_variant) == ("BASE-BADM", ("AA-Flx",), None)
    fluxnet = download_request("FLUXNET", ["US-Ha1", "AR-Bal"])
    assert fluxnet.data_product == "FLUXNET" and fluxnet.data_variant == "FULLSET"
    assert download_request("BASE-BADM", ["US-Ha1"]).data_product == "BASE-BADM"
    with pytest.raises(ToolError) as one_site:
        download_request("BIF", ["US-Ha1"])
    assert one_site.value.details["reason"] == "bif_needs_bulk_site"
    with pytest.raises(ToolError) as bulk:
        download_request("BASE-BADM", ["AA-Net"])
    assert bulk.value.details["reason"] == "bulk_site_needs_bif"
    for frozen in ("FLUXNET2015", "FLUXNET-CH4"):
        with pytest.raises(ToolError) as exc:
            download_request(frozen, ["US-Ha1"])  # type: ignore[arg-type]
        assert exc.value.code == "feature_unavailable"


@pytest.mark.parametrize(
    ("text", "ok"), [("US-Ha1", True), ("us-xsr", True), ("US-Ha", False), ("Harvard", False)]
)
def test_site_id_syntax(text: str, ok: bool) -> None:
    assert is_site_id(text) is ok


def test_fluxnet2015_renames() -> None:
    assert RENAMES["DK-ZaF"] == "GL-ZaF" and RENAMES["NO-Blv"] == "SJ-Blv"
    assert renamed("dk-zaf") == "GL-ZaF" and renamed("US-Ha1") is None
    assert "renamed GL-ZaF" in rename_note("DK-ZaF", "GL-ZaF")
