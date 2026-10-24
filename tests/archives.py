"""Builders for the local-file tests: synthetic archives in the layouts AmeriFlux and FLUXNET use.

Only ``tests/data/AMF_US-CRT_BASE_HH_2-5.csv`` is real (amerifluxr's sample, AmeriFlux
CC-BY-4.0 data, NOTICE). Everything else is generated here: BIF workbooks (with
``example.org`` contacts), an hourly BASE file crossing a year boundary, a FLUXNET v1.3
archive whose ``HH`` member is hourly, FLUXNET2015 SUBSET files and AUX tables, and
hostile archives (zip slip, symbolic link, zip bomb).
"""

from __future__ import annotations

import io
import stat
import zipfile
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

DATA = Path(__file__).parent / "data"
US_CRT_CSV = DATA / "AMF_US-CRT_BASE_HH_2-5.csv"
BIF_HEADER = ("SITE_ID", "GROUP_ID", "VARIABLE_GROUP", "VARIABLE", "DATAVALUE")


# ---------------------------------------------------------------------- BIF


def bif_rows(
    site: str,
    *,
    offsets: Sequence[tuple[str | None, str]] = ((None, "-5"),),
    doi: str = "10.17190/AMF/1246156",
) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = [
        (site, "100", "GRP_LOCATION", "LOCATION_LAT", "41.628495"),
        (site, "100", "GRP_LOCATION", "LOCATION_LONG", "-83.347086"),
        (site, "101", "GRP_IGBP", "IGBP", "CRO"),
        (site, "102", "GRP_DOI", "DOI", doi),
        (
            site,
            "102",
            "GRP_DOI",
            "DOI_CITATION",
            f"Jane Doe (2020), AmeriFlux BASE {site}, Ver. 2-5",
        ),
        (site, "102", "GRP_DOI", "DOI_DATAPRODUCT", "AmeriFlux"),
        (site, "103", "GRP_ACKNOWLEDGEMENT", "ACKNOWLEDGEMENT", "Supported by NSF & NOAA"),
        (site, "104", "GRP_SITE_FUNDING", "SITE_FUNDING", "NOAA & NSF"),
        (site, "105", "GRP_TEAM_MEMBER", "TEAM_MEMBER_NAME", "Jane Doe"),
        (site, "105", "GRP_TEAM_MEMBER", "TEAM_MEMBER_ROLE", "PI"),
        (site, "105", "GRP_TEAM_MEMBER", "TEAM_MEMBER_EMAIL", "jane.doe@example.org"),
        (site, "105", "GRP_TEAM_MEMBER", "TEAM_MEMBER_ADDRESS", "1 Example Road, Testville"),
        (site, "106", "GRP_SHIPPING_ADDRESS", "SHIPPING_ADDRESS", "2 Example Lane, Testville"),
        (site, "107", "GRP_LAND_OWNERSHIP", "LAND_OWNERSHIP", "private"),
        (site, "107", "GRP_LAND_OWNERSHIP", "LAND_OWNER", "John Example"),
        (site, "108", "GRP_SITE_DESC", "SITE_DESC", "Contact desk@example.org for access."),
    ]
    for i, (start, hours) in enumerate(offsets):
        gid = str(200 + i)
        rows.append((site, gid, "GRP_UTC_OFFSET", "UTC_OFFSET", hours))
        if start:
            rows.append((site, gid, "GRP_UTC_OFFSET", "UTC_OFFSET_DATE_START", start))
    return rows


def _col(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def xlsx_bytes(rows: Iterable[Sequence[str]], *, numeric_columns: Iterable[int] = (1,)) -> bytes:
    """A minimal workbook: shared strings for text, numbers stored as <v>."""
    numeric = set(numeric_columns)
    shared: list[str] = []
    index: dict[str, int] = {}
    sheet_rows = []
    for r, row in enumerate([BIF_HEADER, *rows], start=1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{_col(c)}{r}"
            if r > 1 and c in numeric and value.lstrip("-").replace(".", "").isdigit():
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                continue
            if value not in index:
                index[value] = len(shared)
                shared.append(value)
            cells.append(f'<c r="{ref}" t="s"><v>{index[value]}</v></c>')
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    types = "http://schemas.openxmlformats.org/package/2006/content-types"
    head = '<?xml version="1.0"?>'
    parts = {
        "[Content_Types].xml": f'{head}<Types xmlns="{types}"/>',
        "xl/workbook.xml": f'{head}<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
        '<sheet name="BIF" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'{head}<Relationships xmlns="{pkg}"><Relationship Id="rId1" '
        f'Type="{rel}/worksheet" Target="worksheets/data.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<?xml version="1.0"?><sst xmlns="{main}">'
        + "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
        + "</sst>",
        "xl/worksheets/data.xml": f'<?xml version="1.0"?><worksheet xmlns="{main}"><sheetData>'
        + "".join(sheet_rows)
        + "</sheetData></worksheet>",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(name, text)
    return buffer.getvalue()


def bif_csv(rows: Iterable[Sequence[str]]) -> str:
    lines = [",".join(BIF_HEADER)]
    for row in rows:
        lines.append(",".join(f'"{v}"' if "," in v else v for v in row))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- time series


def series(
    start: datetime,
    count: int,
    step: timedelta,
    columns: Sequence[str],
    *,
    stamp: str = "%Y%m%d%H%M",
    single: bool = False,
    value: Callable[[int, str], str] | None = None,
) -> str:
    header = (["TIMESTAMP"] if single else ["TIMESTAMP_START", "TIMESTAMP_END"]) + list(columns)
    lines = [",".join(header)]
    for i in range(count):
        t0 = start + i * step
        stamps = (
            [t0.strftime(stamp)] if single else [t0.strftime(stamp), (t0 + step).strftime(stamp)]
        )
        values = [value(i, c) if value else str(i) for c in columns]
        lines.append(",".join(stamps + values))
    return "\n".join(lines) + "\n"


def hr_base_csv() -> str:
    """Hourly BASE data across New Year 2011/2012, with every -9999 spelling."""

    def value(i: int, column: str) -> str:
        if column == "TA_1_1_1":
            return ["-9999", "-9999.0", "-9999.9"][i] if i < 3 else f"{-5 + i * 0.5:.1f}"
        if column == "FC":
            return "250" if i == 5 else f"{-2 + i * 0.1:.2f}"  # 250 is beyond FC's range
        if column == "SW_IN":
            return "" if i == 4 else str(i * 10)
        return str(i)

    body = series(
        datetime(2011, 12, 31, 18, 0),
        12,
        timedelta(hours=1),
        ["TA_1_1_1", "FC", "SW_IN"],
        value=value,
    )
    return "# Site: US-Ha1,,,\n# Version: 28-5,,,\n" + body


def fluxmet_hourly() -> str:
    """A v1.3 FLUXMET 'HH' member that is hourly, with QC flags."""

    def value(i: int, column: str) -> str:
        if column.endswith("_QC"):
            return str(i % 4)
        if column == "NEE_VUT_REF":
            return f"{-3 + i:.1f}"
        return f"{10 + i:.1f}"

    cols = [
        "TA_F_MDS",
        "TA_F_MDS_QC",
        "TA_ERA",
        "NEE_VUT_REF",
        "NEE_VUT_REF_QC",
        "NEE_CUT_REF",
        "GPP_NT_VUT_REF",
        "SW_IN_F",
        "P_F",
    ]
    return series(datetime(2012, 1, 1, 0, 0), 48, timedelta(hours=1), cols, value=value)


def fluxmet_daily() -> str:
    def value(i: int, column: str) -> str:
        if column.endswith("_QC"):
            return f"{(i % 10) / 10:.1f}"
        return f"{1 + i * 0.1:.2f}"

    return series(
        datetime(2012, 1, 1),
        20,
        timedelta(days=1),
        ["TA_F_MDS", "TA_F_MDS_QC", "NEE_VUT_REF", "NEE_VUT_REF_QC"],
        stamp="%Y%m%d",
        single=True,
        value=value,
    )


# ---------------------------------------------------------------------- archives


def write_zip(path: Path, members: dict[str, str | bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def base_badm_zip(
    directory: Path, *, offsets: Sequence[tuple[str | None, str]] = ((None, "-5"),)
) -> Path:
    return write_zip(
        directory / "AMF_US-CRT_BASE-BADM_2-5.zip",
        {
            "AMF_US-CRT_BASE_HH_2-5.csv": US_CRT_CSV.read_bytes(),
            "AMF_US-CRT_BIF_20201005.xlsx": xlsx_bytes(bif_rows("US-CRT", offsets=offsets)),
        },
    )


def base_hr_zip(directory: Path, version: str = "28-5") -> Path:
    offsets = (("19910101", "-5"), ("20120101", "-6"))
    return write_zip(
        directory / f"AMF_US-Ha1_BASE-BADM_{version}.zip",
        {
            f"AMF_US-Ha1_BASE_HR_{version}.csv": hr_base_csv(),
            "AMF_US-Ha1_BIF_20260901.xlsx": xlsx_bytes(
                bif_rows("US-Ha1", offsets=offsets, doi="10.17190/AMF/1246059")
            ),
        },
    )


def fluxnet_zip(directory: Path) -> Path:
    prefix = "AMF_AR-Bal_FLUXNET"
    tail = "2012-2013_v1.3_r1.csv"
    return write_zip(
        directory / "AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip",
        {
            "README.txt": "README FILE\n",
            "DATA_POLICY_LICENSE_AND_INSTRUCTIONS.txt": "CC-BY-4.0\n",
            f"{prefix}_FLUXMET_HH_{tail}": fluxmet_hourly(),
            f"{prefix}_FLUXMET_DD_{tail}": fluxmet_daily(),
            f"{prefix}_ERA5_HH_1981-2025_v1.3_r1.csv": series(
                datetime(1981, 1, 1), 5, timedelta(hours=1), ["TA_ERA"]
            ),
            f"{prefix}_BIFVARINFO_HH_{tail}": bif_csv(
                [("AR-Bal", "1", "GRP_VAR_INFO", "VAR_INFO_VARNAME", "TA_F_MDS")]
            ),
            f"{prefix}_BIF_{tail}": bif_csv(
                bif_rows("AR-Bal", offsets=((None, "-3"),), doi="10.17190/AMF/2571144")
            ),
        },
    )


def fluxnet2015_subset_zip(directory: Path) -> Path:
    prefix = "FLX_US-Ha1_FLUXNET2015"
    return write_zip(
        directory / f"{prefix}_SUBSET_1991-2012_1-4.zip",
        {
            f"{prefix}_SUBSET_HR_1991-2012_1-4.csv": series(
                datetime(1991, 1, 1), 24, timedelta(hours=1), ["TA_F", "NEE_VUT_REF"]
            ),
            f"{prefix}_SUBSET_DD_1991-2012_1-4.csv": series(
                datetime(1991, 1, 1), 10, timedelta(days=1), ["TA_F"], stamp="%Y%m%d", single=True
            ),
            f"{prefix}_AUXMETEO_1991-2012_1-4.csv": (
                "ID,VARIABLE,PARAMETER,VALUE\n1,TA,ERA_SLOPE,0.98\n2,TA,ERA_INTERCEPT,-0.2\n"
                "3,PA,ERA_SLOPE,1.01\n"
            ),
            f"{prefix}_AUXNEE_1991-2012_1-4.csv": (
                "ID,VARIABLE,YEAR,VALUE\n1,USTAR_MP_METHOD,1991,0.21\n2,USTAR_CP_METHOD,1991,-9999\n"
            ),
        },
    )


def hostile_zip(directory: Path) -> Path:
    """Zip slip, a symbolic link and a zip bomb, beside one honest member."""
    path = directory / "AMF_US-CRT_BASE-BADM_9-9.zip"
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("AMF_US-CRT_BASE_HH_9-9.csv", US_CRT_CSV.read_bytes())
        z.writestr("../AMF_US-CRT_BASE_HR_9-9.csv", "TIMESTAMP_START\n")
        link = zipfile.ZipInfo("AMF_US-CRT_BIF_20990101.xlsx")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "/etc/passwd")
        z.writestr("bomb.csv", b"0" * (4 * 1024 * 1024))
    return path


__all__ = [
    "DATA",
    "US_CRT_CSV",
    "base_badm_zip",
    "base_hr_zip",
    "bif_csv",
    "bif_rows",
    "fluxnet2015_subset_zip",
    "fluxnet_zip",
    "hostile_zip",
    "series",
    "write_zip",
    "xlsx_bytes",
]
