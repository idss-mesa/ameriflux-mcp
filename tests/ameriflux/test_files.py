"""File names, safe zips, timestamps, CSV streaming, xlsx and BIF parsing, path confinement."""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from ameriflux_mcp.ameriflux.files import bif, csvstream, timestamps, xlsx
from ameriflux_mcp.ameriflux.files.filenames import classify
from ameriflux_mcp.ameriflux.files.paths import resolve_dir, resolve_file, roots
from ameriflux_mcp.ameriflux.files.zipsafe import SafeZip
from ameriflux_mcp.config import Config
from ameriflux_mcp.errors import ToolError
from tests import archives

GIB = 1024**3


# ---------------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("AMF_US-CRT_BASE_HH_2-5.csv", ("base", "data", "US-CRT", "HH", None, "2-5", None)),
        ("amf_us-ha1_base_hr_28-5.CSV", ("base", "data", "us-ha1", "HR", None, "28-5", None)),
        ("AMF_US-Ha1_BASE-BADM_28-5.zip", ("base", "archive", "US-Ha1", None, None, "28-5", None)),
        ("AMF_AA-Flx_BIF_CCBY4_20201218.xlsx", ("bif", "bif", "AA-Flx", None, None, None, "CCBY4")),
        ("AMF_US-xSR_BIF_20260901.xlsx", ("bif", "bif", "US-xSR", None, None, None, None)),
        (
            "AMF_US-Ha1_FLUXNET_1991-2025_v1.3_r1.zip",
            ("fluxnet", "archive", "US-Ha1", None, 1991, "v1.3_r1", None),
        ),
        (
            "AMF_AR-Bal_FLUXNET_FLUXMET_HH_2012-2013_v1.3_r1.csv",
            ("fluxnet", "data", "AR-Bal", "HH", 2012, "v1.3_r1", "FLUXMET"),
        ),
        (
            "AMF_AR-Bal_FLUXNET_ERA5_DD_1981-2025_v1.3_r1.csv",
            ("fluxnet", "era", "AR-Bal", "DD", 1981, "v1.3_r1", "ERA5"),
        ),
        (
            "AMF_AR-Bal_FLUXNET_BIFVARINFO_YY_2012-2013_v1.3_r1.csv",
            ("fluxnet", "bifvarinfo", "AR-Bal", "YY", 2012, "v1.3_r1", "BIFVARINFO"),
        ),
        (
            "AMF_AR-Bal_FLUXNET_BIF_2012-2013_v1.3_r1.csv",
            ("fluxnet", "bif", "AR-Bal", None, 2012, "v1.3_r1", "BIF"),
        ),
        (
            "AMF_AR-Bal_FLUXNET_FULLSET_2012-2013_3-7.zip",
            ("fluxnet", "archive", "AR-Bal", None, 2012, "3-7", "FULLSET"),
        ),
        (
            "FLX_US-Ha1_FLUXNET2015_FULLSET_HR_1991-2012_1-4.csv",
            ("fluxnet2015", "data", "US-Ha1", "HR", 1991, "1-4", "FULLSET"),
        ),
        (
            "FLX_US-Ha1_FLUXNET2015_ERAI_DD_1989-2014_1-4.csv",
            ("fluxnet2015", "era", "US-Ha1", "DD", 1989, "1-4", "ERAI"),
        ),
        (
            "FLX_US-Ha1_FLUXNET2015_AUXNEE_1991-2012_1-4.csv",
            ("fluxnet2015", "aux_table", "US-Ha1", None, 1991, "1-4", "AUXNEE"),
        ),
        (
            "FLX_DE-Tha_FLUXNET2015_FULLSET_1996-2014_beta-3.zip",
            ("fluxnet2015", "archive", "DE-Tha", None, 1996, "beta-3", "FULLSET"),
        ),
        (
            "FLX_US-Myb_FLUXNET-CH4_HH_2010-2017_1-1.csv",
            ("fluxnet_ch4", "data", "US-Myb", "HH", 2010, "1-1", None),
        ),
        ("README.txt", ("doc", "readme", None, None, None, None, None)),
    ],
)
def test_classify(name: str, expected: tuple[object, ...]) -> None:
    got = classify(name)
    assert got is not None
    assert (
        got.family,
        got.kind,
        got.site_id,
        got.resolution,
        got.first_year,
        got.version,
        got.variant,
    ) == expected


@pytest.mark.parametrize(
    "name", ["notes.csv", "AMF_US-Ha1_BASE_XX_1-1.csv", "AMF_US-Ha1_FLUXNET_1991_v1.zip", ""]
)
def test_classify_rejects(name: str) -> None:
    assert classify(name) is None


def test_name_properties() -> None:
    fluxmet = classify("AMF_AR-Bal_FLUXNET_FLUXMET_HH_2012-2013_v1.3_r1.csv")
    assert fluxmet and fluxmet.product == "FLUXNET" and fluxmet.is_table and not fluxmet.is_archive
    aux = classify("FLX_US-Ha1_FLUXNET2015_AUXMETEO_1991-2012_1-4.csv")
    assert aux and aux.is_table
    bif_name = classify("AMF_US-CRT_BIF_20201005.xlsx")
    assert bif_name and bif_name.date == "2020-10-05" and not bif_name.is_table


# ---------------------------------------------------------------------- zipsafe


def test_hostile_members_are_refused(tmp_path: Path) -> None:
    path = archives.hostile_zip(tmp_path)
    with SafeZip(path, max_member_bytes=GIB) as archive:
        refused = {m.name: m.refused for m in archive.members}
        assert refused["AMF_US-CRT_BASE_HH_9-9.csv"] is None
        assert "outside the archive" in (refused["../AMF_US-CRT_BASE_HR_9-9.csv"] or "")
        assert refused["AMF_US-CRT_BIF_20990101.xlsx"] == "symbolic link"
        assert "zip bomb" in (refused["bomb.csv"] or "")
        assert archive.read("AMF_US-CRT_BASE_HH_9-9.csv").startswith(b"# Site: US-CRT")
        for name in ("bomb.csv", "AMF_US-CRT_BIF_20990101.xlsx", "../AMF_US-CRT_BASE_HR_9-9.csv"):
            with pytest.raises(ToolError) as exc:
                archive.open(name)
            assert exc.value.details["reason"] == "unsafe_member"
    assert not (tmp_path.parent / "AMF_US-CRT_BASE_HR_9-9.csv").exists()


def test_size_cap_basename_lookup_and_bad_zips(tmp_path: Path) -> None:
    path = archives.base_badm_zip(tmp_path)
    with SafeZip(path, max_member_bytes=1024) as archive:
        assert all("larger than" in (m.refused or "") for m in archive.members)
    with SafeZip(path, max_member_bytes=GIB) as archive:
        assert archive.member("amf_us-crt_base_hh_2-5.CSV").name == "AMF_US-CRT_BASE_HH_2-5.csv"
        with pytest.raises(ToolError) as missing:
            archive.member("nope.csv")
        assert missing.value.code == "not_found"
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    with pytest.raises(ToolError) as bad:
        SafeZip(junk, max_member_bytes=GIB)
    assert bad.value.details["reason"] == "bad_zip"


# ---------------------------------------------------------------------- timestamps


def test_timestamps() -> None:
    assert timestamps.iso("201101010030") == "2011-01-01T00:30"
    assert timestamps.iso("20110101") == "2011-01-01"
    assert timestamps.iso("201101") == "2011-01" and timestamps.iso("2011") == "2011"
    assert timestamps.iso("20111301") is None
    assert timestamps.step_minutes("201112312330", "201201010000") == 30  # year rollover
    assert timestamps.step_minutes("20150701", "20150707") == 10080
    assert timestamps.window_bound("2012-06-01T12:00", field="start") == "201206011200"
    assert timestamps.padded("2012", 12, end=True) == "201299999999"
    assert timestamps.padded("2012", 8, end=False) == "20120000"
    for bad in ("June 2012", "2012-13", "12345"):
        with pytest.raises(ToolError):
            timestamps.window_bound(bad, field="start")
    offsets = [("19910101", -5.0), ("20120101", -6.0)]
    assert timestamps.utc_offset_for("201112312300", offsets) == -5.0
    assert timestamps.utc_offset_for("201201010000", offsets) == -6.0
    assert timestamps.utc_offset_for("198001010000", offsets) == -5.0
    assert timestamps.to_utc("201101010000", -5) == "2011-01-01T05:00Z"
    assert timestamps.to_utc("20110101", -5) is None


# ---------------------------------------------------------------------- csvstream


def scan(text: str, **kw: object) -> csvstream.ScanResult:
    return csvstream.scan(io.BytesIO(text.encode()), **kw)  # type: ignore[arg-type]


def test_scan_base_file() -> None:
    result = scan(archives.hr_base_csv())
    assert result.header_lines == ["# Site: US-Ha1", "# Version: 28-5"]
    assert result.timestamp_columns == ["TIMESTAMP_START", "TIMESTAMP_END"]
    assert result.step_minutes == 60 and result.rows_matched == 12
    ta = result.stats["TA_1_1_1"]
    assert ta.missing == 3 and ta.count == 9  # -9999, -9999.0, -9999.9
    assert result.stats["SW_IN"].missing == 1  # empty cell
    assert (result.first, result.last) == ("201112311800", "201201010500")


def test_scan_window_ranges_and_rows() -> None:
    result = scan(
        archives.hr_base_csv(),
        columns=["fc"],
        start="2012",
        end="201201010200",
        want_rows=True,
        ranges={"FC": (-105.0, 105.0)},
    )
    assert result.selected == ["FC"] and result.stopped_at_end
    assert [r[0] for r in result.rows] == ["201201010000", "201201010100", "201201010200"]
    full = scan(archives.hr_base_csv(), ranges={"FC": (-105.0, 105.0)})
    assert full.stats["FC"].out_of_range == 1 and full.stats["FC"].maximum == 250.0
    paged = scan(archives.hr_base_csv(), want_rows=True, offset=2, max_rows=3)
    assert len(paged.rows) == 3 and paged.more_rows and paged.rows[0][0] == "201112312000"


def test_scan_qc_rules() -> None:
    hourly = scan(archives.fluxmet_hourly(), columns=["NEE_VUT_REF"], qc=csvstream.QcRule("max", 1))
    nee = hourly.stats["NEE_VUT_REF"]
    assert hourly.qc_columns == {"NEE_VUT_REF": "NEE_VUT_REF_QC"}
    assert nee.qc_filtered == 24 and nee.count == 24  # flags 2 and 3 of 0..3
    daily = scan(
        archives.fluxmet_daily(), columns=["TA_F_MDS"], qc=csvstream.QcRule("min_fraction", 0.5)
    )
    assert daily.stats["TA_F_MDS"].qc_filtered == 10
    assert daily.timestamp_columns == ["TIMESTAMP"] and daily.step_minutes is None


def test_scan_aux_tables_and_errors() -> None:
    aux = "ID,VARIABLE,PARAMETER,VALUE\n1,TA,ERA_SLOPE,0.98\n2,PA,ERA_SLOPE,-9999\n"
    result = scan(aux, require_timestamps=False)
    assert result.timestamp_columns == [] and result.stats["VALUE"].count == 1
    assert result.stats["VARIABLE"].text_values == ["TA", "PA"]
    with pytest.raises(ToolError) as no_ts:
        scan(aux)
    assert no_ts.value.details["reason"] == "no_timestamps"
    with pytest.raises(ToolError):
        scan(aux, require_timestamps=False, start="2012")
    with pytest.raises(ToolError) as unknown:
        scan(archives.hr_base_csv(), columns=["TA_1_1_2"])
    assert unknown.value.details["didYouMean"]["TA_1_1_2"] == ["TA_1_1_1"]
    with pytest.raises(ToolError):
        scan("# only a comment\n")


def test_scan_budget_stops() -> None:
    from datetime import datetime, timedelta

    big = archives.series(datetime(2000, 1, 1), 5000, timedelta(minutes=30), ["TA"])
    by_bytes = scan(big, max_bytes=1024)
    assert by_bytes.truncated_reason == "budget" and by_bytes.rows_scanned < 5000
    ticks = iter(range(0, 10**6, 100))
    by_time = csvstream.scan(
        io.BytesIO(big.encode()), time_budget_s=50, clock=lambda: float(next(ticks))
    )
    assert by_time.truncated_reason == "budget"
    assert scan(big).truncated_reason is None


# ---------------------------------------------------------------------- xlsx and BIF


def test_xlsx_and_bif_privacy() -> None:
    data = archives.xlsx_bytes(archives.bif_rows("US-CRT", offsets=(("20100101", "-5"),)))
    rows = xlsx.read_rows(data, label="t.xlsx", max_bytes=GIB)
    assert rows[0] == list(archives.BIF_HEADER) and rows[1][1] == "100"
    parsed = bif.parse(rows, label="t.xlsx")
    assert parsed.withheld == 5  # email, two addresses, land owner, an email inside SITE_DESC
    flat = repr([e.values for e in parsed.entries])
    assert "@" not in flat and "Example Road" not in flat and "John Example" not in flat
    assert bif.utc_offsets(parsed)[0].date_start == "20100101"
    assert bif.first_value(parsed.groups("GRP_DOI"), "DOI") == "10.17190/AMF/1246156"
    ack = parsed.groups("GRP_ACKNOWLEDGEMENT")[0].values["ACKNOWLEDGEMENT"]
    assert ack == "Supported by NSF & NOAA"  # XML entities decoded
    allowed = bif.parse(rows, label="t.xlsx", allow_personal=True)
    assert allowed.withheld == 0 and "jane.doe@example.org" in repr(allowed.entries)


def test_bif_csv_and_errors() -> None:
    text = archives.bif_csv(archives.bif_rows("AR-Bal"))
    parsed = bif.parse(bif.rows_from_bytes(text.encode(), label="b.csv", max_bytes=GIB), label="b")
    assert parsed.sites == ["AR-Bal"] and parsed.withheld == 5
    with pytest.raises(ToolError) as not_bif:
        bif.parse([["A", "B"], ["1", "2"]], label="x")
    assert not_bif.value.details["reason"] == "not_bif"
    with pytest.raises(ToolError):
        bif.parse([], label="x")
    with pytest.raises(ToolError) as bad:
        xlsx.read_rows(b"PK\x03\x04garbage", label="g.xlsx", max_bytes=GIB)
    assert bad.value.details["reason"] == "bad_zip"


# ---------------------------------------------------------------------- paths


def test_paths_are_confined(config: Config, tmp_path: Path) -> None:
    downloads = config.downloads.directory
    downloads.mkdir(parents=True)
    extra = tmp_path / "fluxnet2015"
    extra.mkdir()
    cfg = config.model_copy(deep=True)
    cfg.local.roots = [extra]
    assert roots(cfg) == [downloads, extra]
    inside = archives.base_badm_zip(downloads)
    got = resolve_file("AMF_US-CRT_BASE-BADM_2-5.zip::AMF_US-CRT_BASE_HH_2-5.csv", cfg)
    assert got.path == inside and got.member == "AMF_US-CRT_BASE_HH_2-5.csv"
    assert got.display == "AMF_US-CRT_BASE-BADM_2-5.zip::AMF_US-CRT_BASE_HH_2-5.csv"
    outside = tmp_path / "secret.csv"
    outside.write_text("x")
    (downloads / "link.csv").symlink_to(outside)
    for text in (str(outside), "../secret.csv", "link.csv", "missing.zip", "", str(downloads)):
        with pytest.raises(ToolError) as exc:
            resolve_file(text, cfg)
        assert exc.value.details["reason"] == "outside_local_roots"
    assert resolve_dir(None, cfg) == [(downloads, downloads), (extra, extra)]
    with pytest.raises(ToolError):
        resolve_dir(str(tmp_path), cfg)
    assert os.path.exists(outside)


def test_xlsx_cell_types_and_sheet_fallback() -> None:
    import zipfile

    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = (
        f'<worksheet xmlns="{main}"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>SITE_ID</t></is></c>'
        '<c r="C1" t="s"><v>0</v></c><c t="b"><v>1</v></c></row>'
        '<row r="2"><c r="B2"><v>12.5</v></c><c r="C2" t="s"><v>9</v></c>'
        '<c r="D2" t="str"><v>formula text</v></c></row>'
        "<row/></sheetData></worksheet>"
    )
    strings = f'<sst xmlns="{main}"><si><r><t>Rich </t></r><r><t>text</t></r></si></sst>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", strings)
    rows = xlsx.read_rows(buffer.getvalue(), label="f.xlsx", max_bytes=GIB)
    assert rows == [["SITE_ID", "", "Rich text", "TRUE"], ["", "12.5", "", "formula text"]]
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("docProps/app.xml", "<x/>")
    with pytest.raises(ToolError) as no_sheet:
        xlsx.read_rows(empty.getvalue(), label="e.xlsx", max_bytes=GIB)
    assert no_sheet.value.details["reason"] == "bad_xlsx"
    broken = io.BytesIO()
    with zipfile.ZipFile(broken, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", "<not xml")
    with pytest.raises(ToolError):
        xlsx.read_rows(broken.getvalue(), label="b.xlsx", max_bytes=GIB)
