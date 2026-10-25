"""File-name grammar of AmeriFlux, FLUXNET and FLUXNET2015 products (RESEARCH.md section 6).

Matching is case-insensitive; the site ID keeps the case the name uses (AmeriFlux writes
``US-Ha1`` but ``US-CRT``, so no rule recovers it).

| Family | Pattern |
| --- | --- |
| BASE | ``AMF_<S>_BASE_(HH|HR)_<X-Y>.csv``, ``AMF_<S>_BASE-BADM_<X-Y>.zip`` |
| BIF | ``AMF_<S|AA-Net|AA-Flx>_BIF_[CCBY4_|LEGACY_]YYYYMMDD.xlsx`` |
| FLUXNET v1.3+ | ``<NET>_<S>_FLUXNET_<YS>-<YE>_v<N>[.<M>]_r<N>.zip`` (FLUXNET Shuttle pattern, |
| | BSD-3, NOTICE); members ``…_FLUXNET_(FLUXMET|ERA5|BIFVARINFO)_<T>_…csv``, ``…_BIF_…csv`` |
| FLUXNET before v1.3 | ``<NET>_<S>_FLUXNET_(FULLSET|SUBSET)[_<T>]_<YS>-<YE>_<n-n>.(zip|csv)`` |
| FLUXNET2015 | ``FLX_<S>_FLUXNET2015_(FULLSET|SUBSET|ERAI|AUXMETEO|AUXNEE)[_<T>]_<YS>-<YE>_`` |
| | ``(<n-n>|beta-<n>).(zip|csv)`` |
| FLUXNET-CH4 | ``FLX_<S>_FLUXNET-CH4_(HH|HR|DD)_<YS>-<YE>_<n-n>.csv`` (recognized; read in v0.2) |

In ONEFlux v1.3 names the ``HH`` token is the finest step, half-hourly or hourly, so the
step is read from the timestamps (E32); FLUXNET2015 and BASE write ``HR`` for hourly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Family = Literal["base", "bif", "fluxnet", "fluxnet2015", "fluxnet_ch4", "doc"]
Kind = Literal["data", "era", "bifvarinfo", "bif", "aux_table", "archive", "readme", "license"]

_SITE = r"([A-Z]{2}-[A-Z0-9]{3})"
_RES = r"(HH|HR|DD|WW|MM|YY)"
_YEARS = r"(\d{4})-(\d{4})"

BASE_CSV = re.compile(rf"^AMF_{_SITE}_BASE_(HH|HR)_(\d+-\d+)\.CSV$", re.I)
BASE_ZIP = re.compile(rf"^AMF_{_SITE}_BASE-BADM_(\d+-\d+)\.ZIP$", re.I)
BIF_XLSX = re.compile(r"^AMF_([A-Z]{2}-[A-Z0-9]{3})_BIF_(?:(CCBY4|LEGACY)_)?(\d{8})\.XLSX$", re.I)
#: FLUXNET Shuttle ``_FLUXNET_ZIP_PATTERN`` (shuttle.py line 68, applied with IGNORECASE).
FLUXNET_ZIP = re.compile(
    r"^([A-Z]{2,10})_([A-Z]{2}-[A-Za-z0-9]{3})_FLUXNET_(\d{4})-(\d{4})_(v\d+(?:\.\d+)?)_(r\d+)\.zip$",
    re.I,
)
FLUXNET_MEMBER = re.compile(
    rf"^([A-Z]{{2,10}})_{_SITE}_FLUXNET_(FLUXMET|ERA5|BIFVARINFO)_{_RES}_{_YEARS}_"
    r"(v\d+(?:\.\d+)?)_(r\d+)\.CSV$",
    re.I,
)
FLUXNET_BIF = re.compile(
    rf"^([A-Z]{{2,10}})_{_SITE}_FLUXNET_BIF_{_YEARS}_(v\d+(?:\.\d+)?)_(r\d+)\.CSV$", re.I
)
FLUXNET_OLD = re.compile(
    rf"^([A-Z]{{2,10}})_{_SITE}_FLUXNET_(FULLSET|SUBSET)(?:_{_RES})?_{_YEARS}_(\d+-\d+)\.(ZIP|CSV)$",
    re.I,
)
FLUXNET2015 = re.compile(
    rf"^FLX_{_SITE}_FLUXNET2015_(FULLSET|SUBSET|ERAI|AUXMETEO|AUXNEE)(?:_{_RES})?_{_YEARS}_"
    r"(\d+-\d+|BETA-\d+)\.(ZIP|CSV)$",
    re.I,
)
FLUXNET_CH4 = re.compile(rf"^FLX_{_SITE}_FLUXNET-CH4_(HH|HR|DD)_{_YEARS}_(\d+-\d+)\.CSV$", re.I)
DOCS = {
    "README.TXT": "readme",
    "DATA_POLICY_LICENSE_AND_INSTRUCTIONS.TXT": "license",
}


@dataclass(frozen=True)
class FileName:
    name: str
    family: Family
    kind: Kind
    site_id: str | None = None
    resolution: str | None = None
    first_year: int | None = None
    last_year: int | None = None
    version: str | None = None
    #: FULLSET, SUBSET, ERAI, AUXMETEO, AUXNEE, FLUXMET, ERA5, BIFVARINFO, CCBY4, LEGACY.
    variant: str | None = None
    network: str | None = None
    #: BIF file date (YYYY-MM-DD).
    date: str | None = None

    @property
    def product(self) -> str:
        return {
            "base": "BASE-BADM",
            "bif": "BIF",
            "fluxnet": "FLUXNET",
            "fluxnet2015": "FLUXNET2015",
            "fluxnet_ch4": "FLUXNET-CH4",
        }.get(self.family, "")

    @property
    def is_archive(self) -> bool:
        return self.kind == "archive"

    @property
    def is_table(self) -> bool:
        """A CSV that :mod:`csvstream` can read (time series or aux table)."""
        return self.name.upper().endswith(".CSV") and self.kind in (
            "data",
            "era",
            "aux_table",
        )


def _site(text: str) -> str:
    """Site IDs keep the case the file name uses: AmeriFlux writes US-Ha1 but US-CRT."""
    return text


def classify(name: str) -> FileName | None:
    """Recognize one file or zip-member name (a basename); ``None`` if it is none of ours."""
    base = name.rsplit("/", 1)[-1]
    upper = base.upper()
    if upper in DOCS:
        return FileName(base, "doc", DOCS[upper])  # type: ignore[arg-type]
    if m := BASE_CSV.match(base):
        return FileName(
            base, "base", "data", _site(m.group(1)), m.group(2).upper(), version=m.group(3)
        )
    if m := BASE_ZIP.match(base):
        return FileName(base, "base", "archive", _site(m.group(1)), version=m.group(2))
    if m := BIF_XLSX.match(base):
        date = m.group(3)
        return FileName(
            base,
            "bif",
            "bif",
            _site(m.group(1)),
            variant=(m.group(2) or "").upper() or None,
            date=f"{date[:4]}-{date[4:6]}-{date[6:]}",
        )
    if m := FLUXNET_ZIP.match(base):
        return FileName(
            base,
            "fluxnet",
            "archive",
            _site(m.group(2)),
            first_year=int(m.group(3)),
            last_year=int(m.group(4)),
            version=f"{m.group(5)}_{m.group(6)}".lower(),
            network=m.group(1).upper(),
        )
    if m := FLUXNET_MEMBER.match(base):
        variant = m.group(3).upper()
        kind: Kind = {"FLUXMET": "data", "ERA5": "era", "BIFVARINFO": "bifvarinfo"}[variant]  # type: ignore[assignment]
        return FileName(
            base,
            "fluxnet",
            kind,
            _site(m.group(2)),
            m.group(4).upper(),
            int(m.group(5)),
            int(m.group(6)),
            f"{m.group(7)}_{m.group(8)}".lower(),
            variant,
            m.group(1).upper(),
        )
    if m := FLUXNET_BIF.match(base):
        return FileName(
            base,
            "fluxnet",
            "bif",
            _site(m.group(2)),
            None,
            int(m.group(3)),
            int(m.group(4)),
            f"{m.group(5)}_{m.group(6)}".lower(),
            "BIF",
            m.group(1).upper(),
        )
    if m := FLUXNET_OLD.match(base):
        archive = m.group(8).upper() == "ZIP"
        return FileName(
            base,
            "fluxnet",
            "archive" if archive else "data",
            _site(m.group(2)),
            (m.group(4) or "").upper() or None,
            int(m.group(5)),
            int(m.group(6)),
            m.group(7),
            m.group(3).upper(),
            m.group(1).upper(),
        )
    if m := FLUXNET2015.match(base):
        variant = m.group(2).upper()
        archive = m.group(7).upper() == "ZIP"
        if archive:
            kind = "archive"
        elif variant in ("AUXMETEO", "AUXNEE"):
            kind = "aux_table"
        elif variant == "ERAI":
            kind = "era"
        else:
            kind = "data"
        return FileName(
            base,
            "fluxnet2015",
            kind,
            _site(m.group(1)),
            (m.group(3) or "").upper() or None,
            int(m.group(4)),
            int(m.group(5)),
            m.group(6).lower(),
            variant,
            "FLX",
        )
    if m := FLUXNET_CH4.match(base):
        return FileName(
            base,
            "fluxnet_ch4",
            "data",
            _site(m.group(1)),
            m.group(2).upper(),
            int(m.group(3)),
            int(m.group(4)),
            m.group(5),
            network="FLX",
        )
    return None


__all__ = ["FileName", "classify"]
