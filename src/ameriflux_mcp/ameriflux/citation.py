"""Per-site data citations (DESIGN.md D9, RESEARCH.md section 4).

Source of truth is ``GET v1/DOI/{SITE}/{AmeriFlux|FLUXNET|FLUXNET2015}``:

* **AmeriFlux** (BASE-BADM, and BIF, which has no DOI of its own: ``DOI/{SITE}/BIF``
  answers ``{}``, E20, E41) and **FLUXNET** (FLUXNET-1F): ``DOI_CITATION`` verbatim. It
  carries the product version ("Ver. 28-5", "Ver. v1.3_r1 (1991-2025)") that generic
  DOI services lack.
* **FLUXNET2015**: ``DOI_CITATION`` is null (E51), so the citation is constructed the
  way the FLUXNET DOI landing page renders it (E60): authors, the Tier Two year range,
  the title and the DOI.
* **DataCite** is the last resort, used only when the DOI API fails and the catalog
  knows the DOI: no version, and year and publisher differ (E19), so it comes with a
  ``versionMissing`` warning.

DOI records carry contributor emails; they are cached in memory only (D19, D22) and
never leave this module.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from ameriflux_mcp.ameriflux.catalog import SiteRecord
from ameriflux_mcp.ameriflux.client import Fetched
from ameriflux_mcp.ameriflux.endpoints import DOI
from ameriflux_mcp.errors import AmeriFluxApiError

if TYPE_CHECKING:
    from ameriflux_mcp.context import ToolContext

CitationProduct = Literal["BASE-BADM", "BIF", "FLUXNET", "FLUXNET2015"]
CitationSource = Literal["amfcdn", "constructed", "datacite"]
DOI_SEGMENTS: dict[str, str] = {
    "BASE-BADM": "AmeriFlux",
    "BIF": "AmeriFlux",
    "FLUXNET": "FLUXNET",
    "FLUXNET2015": "FLUXNET2015",
}
#: Catalog ``doi`` keys per DOI segment (FLUXNET2015 DOIs are not in the catalog).
CATALOG_DOI_KEYS: dict[str, str] = {"AmeriFlux": "AmeriFlux", "FLUXNET": "FLUXNET"}
DATACITE_URL = "https://api.datacite.org/dois/"
VERSION_RE = re.compile(r"\bVer\. (.+?), AmeriFlux AMP")
YEAR_RE = re.compile(r"\((\d{4})\)")
_SPACES = re.compile(r"\s+")
VERSION_MISSING = (
    "versionMissing: the AmeriFlux DOI service was unavailable, so this citation comes from "
    "DataCite, which records no product version and may give a different year and publisher. "
    "Check the site's DOI page before publishing."
)


@dataclass(frozen=True)
class Contributor:
    first: str
    middle: str
    last: str
    role: str | None
    institution: str | None
    ordinal: int | None

    @property
    def name(self) -> str:
        return _SPACES.sub(" ", f"{self.first} {self.middle} {self.last}").strip()

    @property
    def bibtex_name(self) -> str:
        given = _SPACES.sub(" ", f"{self.first} {self.middle}").strip()
        return f"{self.last}, {given}" if given else self.last


@dataclass(frozen=True)
class Reference:
    usage: str | None
    doi: str | None
    paper: str | None


@dataclass(frozen=True)
class DoiRecord:
    doi: str
    citation: str | None
    title: str | None
    policy: str | None
    description: str | None
    site_page: str | None
    country: str | None
    contributors: tuple[Contributor, ...] = ()
    sponsors: tuple[str, ...] = ()
    organizations: tuple[str, ...] = ()
    references: tuple[Reference, ...] = ()

    @property
    def authors(self) -> tuple[Contributor, ...]:
        """Contributors in the citation's author list (role Author; all if none is)."""
        authors = tuple(c for c in self.contributors if (c.role or "").lower() == "author")
        return authors or self.contributors


@dataclass
class SiteCitation:
    site_id: str
    product: str
    doi: str
    text: str
    source: CitationSource
    title: str | None = None
    version: str | None = None
    year: str | None = None
    policy: str | None = None
    authors: list[str] = field(default_factory=list)
    bibtex_authors: list[str] = field(default_factory=list)
    sponsors: list[str] = field(default_factory=list)
    site_page: str | None = None
    warnings: list[str] = field(default_factory=list)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _ordinal(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _orgs(rows: Any) -> tuple[str, ...]:
    if not isinstance(rows, list):
        return ()
    return tuple(
        _text(r.get("DOI_ORGANIZATION"))
        for r in rows
        if isinstance(r, Mapping) and _text(r.get("DOI_ORGANIZATION"))
    )


def parse_doi(payload: Mapping[str, Any]) -> DoiRecord:
    """A ``v1/DOI`` object (required keys already checked by ``unwrap``)."""
    info = payload.get("DOI_INFO") or {}
    contributors = sorted(
        (
            Contributor(
                first=_text(r.get("DOI_CONTRIBUTOR_FIRST_NAME")),
                middle=_text(r.get("DOI_CONTRIBUTOR_MIDDLE_NAME")),
                last=_text(r.get("DOI_CONTRIBUTOR_LAST_NAME")),
                role=_text(r.get("DOI_CONTRIBUTOR_ROLE")) or None,
                institution=_text(r.get("DOI_CONTRIBUTOR_INSTITUTION")) or None,
                ordinal=_ordinal(r.get("DOI_CONTRIBUTOR_ORDINAL")),
            )
            for r in payload.get("DOI_CONTRIBUTOR") or []
            if isinstance(r, Mapping)
        ),
        key=lambda c: (c.ordinal is None, c.ordinal or 0),
    )
    references = tuple(
        Reference(
            usage=_text(r.get("REFERENCE_USAGE")) or None,
            doi=_text(r.get("REFERENCE_DOI")) or None,
            paper=_text(r.get("REFERENCE_PAPER")) or None,
        )
        for r in payload.get("REFERENCES") or []
        if isinstance(r, Mapping)
    )
    return DoiRecord(
        doi=_text(info.get("DOI")),
        citation=_text(info.get("DOI_CITATION")) or None,
        title=_text(info.get("title")) or None,
        policy=_text(info.get("DATA_POLICY")) or None,
        description=_text(info.get("doi_description")) or None,
        site_page=_text(info.get("amf_site_page") or info.get("flx_site_page")) or None,
        country=_text(info.get("country")) or None,
        contributors=tuple(c for c in contributors if c.name),
        sponsors=_orgs(payload.get("DOI_SPONSOR_ORGANIZATION")),
        organizations=_orgs(payload.get("DOI_CONTRIBUTOR_ORGANIZATION")),
        references=references,
    )


async def doi_record(ctx: ToolContext, site_id: str, segment: str) -> DoiRecord | None:
    """The DOI record of one site and product segment; ``None`` when AmeriFlux has none."""
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise RuntimeError("no upstream client")
    payload = await ctx.client.fetch(DOI, stats=ctx.stats, site=site_id, product=segment)
    if payload is None:
        return None
    record = parse_doi(payload)
    return record if record.doi else None


def fluxnet2015_text(record: SiteRecord, doi: DoiRecord) -> str:
    """``Authors (1991-2012) FLUXNET2015 US-Ha1 Site Name, Dataset. https://doi.org/…`` (E60)."""
    authors = ", ".join(c.name for c in doi.authors)
    tiers = record.fluxnet2015
    years = (tiers.tier2 or tiers.ccby) if tiers else None
    title = doi.title or f"FLUXNET2015 {record.site_id} {record.name}"
    lead = f"{authors} ({years})" if years else authors
    return f"{lead} {title}, Dataset. https://doi.org/{doi.doi}".strip()


def from_doi_record(record: SiteRecord, product: CitationProduct, doi: DoiRecord) -> SiteCitation:
    if doi.citation:
        text, source = doi.citation, "amfcdn"
    else:
        text, source = fluxnet2015_text(record, doi), "constructed"
    version = VERSION_RE.search(text)
    year = YEAR_RE.search(text)
    return SiteCitation(
        site_id=record.site_id,
        product=product,
        doi=doi.doi,
        text=text,
        source=source,  # type: ignore[arg-type]
        title=doi.title,
        version=version.group(1) if version else None,
        year=year.group(1) if year else None,
        policy=doi.policy,
        authors=[c.name for c in doi.authors],
        bibtex_authors=[c.bibtex_name for c in doi.authors],
        sponsors=list(doi.sponsors),
        site_page=doi.site_page,
    )


def parse_datacite(fetched: Fetched) -> dict[str, Any]:
    """The few DataCite fields a fallback citation needs (no emails in DataCite records)."""
    try:
        attributes = json.loads(fetched.body)["data"]["attributes"]
    except (ValueError, KeyError, TypeError):
        raise AmeriFluxApiError(
            fetched.status,
            "not a DataCite DOI record",
            fetched.endpoint,
            kind="decode",
            service="DataCite",
        ) from None
    titles = attributes.get("titles") or [{}]
    return {
        "creators": [
            _text(c.get("name")) for c in attributes.get("creators") or [] if _text(c.get("name"))
        ],
        "title": _text(titles[0].get("title")) or None,
        "publisher": _text(attributes.get("publisher")) or None,
        "year": str(attributes["publicationYear"]) if attributes.get("publicationYear") else None,
        "version": _text(attributes.get("version")) or None,
    }


async def datacite_citation(
    ctx: ToolContext, record: SiteRecord, product: CitationProduct, doi: str
) -> SiteCitation:
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise RuntimeError("no upstream client")
    meta = await ctx.client.fetch_url(
        DATACITE_URL + doi,
        family="citations",
        parse=parse_datacite,
        stats=ctx.stats,
        accept="application/vnd.api+json",
    )
    creators: Sequence[str] = meta["creators"]
    title = meta["title"] or f"{record.site_id} {record.name}"
    parts = [f"{'; '.join(creators)} ({meta['year']})" if meta["year"] else "; ".join(creators)]
    parts.append(title)
    if meta["version"]:
        parts.append(f"Ver. {meta['version']}")
    if meta["publisher"]:
        parts.append(meta["publisher"])
    text = ", ".join(p for p in parts if p) + f", (Dataset). https://doi.org/{doi}"
    return SiteCitation(
        site_id=record.site_id,
        product=product,
        doi=doi,
        text=text,
        source="datacite",
        title=title,
        version=meta["version"],
        year=meta["year"],
        policy=record.policy,
        authors=list(creators),
        bibtex_authors=list(creators),
        warnings=[] if meta["version"] else [VERSION_MISSING],
    )


def bibtex(citation: SiteCitation) -> str:
    """A ``@misc`` entry (DOI, version and AmeriFlux's own title)."""
    key = re.sub(r"[^A-Za-z0-9]+", "_", f"{citation.site_id}_{citation.product}").strip("_")
    publisher = "FLUXNET" if citation.product == "FLUXNET2015" else "AmeriFlux AMP"
    if citation.source == "datacite":
        publisher = ""
    fields = {
        "author": " and ".join(f"{{{a}}}" if "," not in a else a for a in citation.bibtex_authors),
        "title": f"{{{citation.title}}}" if citation.title else None,
        "year": citation.year,
        "version": citation.version,
        "publisher": publisher or None,
        "howpublished": "Dataset",
        "doi": citation.doi,
        "url": f"https://doi.org/{citation.doi}",
    }
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
    return f"@misc{{{key},\n{body}\n}}"


__all__ = [
    "CATALOG_DOI_KEYS",
    "DOI_SEGMENTS",
    "VERSION_MISSING",
    "CitationProduct",
    "Contributor",
    "DoiRecord",
    "Reference",
    "SiteCitation",
    "bibtex",
    "datacite_citation",
    "doi_record",
    "fluxnet2015_text",
    "from_doi_record",
    "parse_datacite",
    "parse_doi",
]
