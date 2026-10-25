"""``amf_download_data``: consented downloads through AmeriFlux's logged route (build step 7).

stdio only, behind ``downloads.enabled`` (DESIGN.md D11-D18). One tool, two phases:

* ``confirm=false`` (default) returns a **plan**: the exact request AmeriFlux would
  receive (identity values masked; the intended use and description in full, because
  that is what the site PIs read), the eligible and ineligible sites, the data policy
  and its obligations, and any local copies. Nothing is sent.
* ``confirm=true`` with ``accept_data_policy`` equal to the plan's policy sends one
  ``POST v1/data_download`` with the configured identity, records the returned links
  in the ledger, and transfers each file with the checks of
  :mod:`ameriflux_mcp.ameriflux.downloads`.

The identity and the disclosed text come only from configuration (D12); no argument
can supply or change them. Each confirmed call notifies the PIs again, so the tool is
not idempotent (D14); a file already present is kept, not fetched twice.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import Field

from ameriflux_mcp.ameriflux.catalog import SiteRecord
from ameriflux_mcp.ameriflux.client import AmeriFluxClient
from ameriflux_mcp.ameriflux.downloads import (
    MANIFEST_SCHEMA,
    DownloadManager,
    Outcome,
    manifest_path,
    utc_now,
    write_json,
)
from ameriflux_mcp.ameriflux.files.filenames import classify
from ameriflux_mcp.ameriflux.files.inventory import version_key, walk
from ameriflux_mcp.ameriflux.identity import (
    DEFAULT_PROFILE,
    Identity,
    Profile,
    configured_profile,
    identity_status,
)
from ameriflux_mcp.ameriflux.ledger import Skipped
from ameriflux_mcp.ameriflux.policy import Obligation, effective_policy, obligations
from ameriflux_mcp.ameriflux.privacy import strip_emails
from ameriflux_mcp.ameriflux.products import (
    BULK_SITES,
    Policy,
    Product,
    download_request,
    info,
    normalize_policy,
    normalize_product,
    validate,
)
from ameriflux_mcp.ameriflux.resolve import resolve_sites
from ameriflux_mcp.context import ToolContext
from ameriflux_mcp.errors import (
    IDENTITY_GUIDE,
    AmeriFluxApiError,
    ToolError,
    identity_required_error,
)
from ameriflux_mcp.models.common import AmfInput, AmfOutput, ToolResultBase
from ameriflux_mcp.registry import register_tool
from ameriflux_mcp.tools._common import compact_years, merge_notes, source
from ameriflux_mcp.tools.availability import ObligationOut, _empty_reason, _read_years
from ameriflux_mcp.tools.citation import _cite_one
from ameriflux_mcp.tools.sites import site_index

MAX_SITES = 20
MASKED = "configured (not shown)"
MISSING = "not configured"
SENT_TO = "AmeriFlux, by POST amfcdn.lbl.gov/api/v1/data_download"
RECIPIENTS = (
    "the principal investigators (PIs) of each requested site",
    "the AmeriFlux Data Download Log (visible to logged-in AmeriFlux users)",
)
DOWNLOAD_ENDPOINTS = [
    "POST amfcdn.lbl.gov/api/v1/data_download",
    "HEAD ftp.fluxdata.org/.ameriflux_downloads/{product}/{file}",
    "GET ftp.fluxdata.org/.ameriflux_downloads/{product}/{file}",
    "GET amfcdn.lbl.gov/api/v1/data_availability/AmeriFlux/{product}/{policy}",
    "GET amfcdn.lbl.gov/api/v1/DOI/{site}/{product}",
]
#: Keys of the upstream manifest's data_files rows that are copied (nothing else).
MANIFEST_KEYS = (
    "site_id",
    "filename",
    "start_year",
    "end_year",
    "version",
    "file_type",
    "timestamp",
)
DISK_MARGIN_BYTES = 64 * 1024 * 1024


class DownloadIn(AmfInput):
    sites: list[str] = Field(
        min_length=1,
        max_length=MAX_SITES,
        description="Site IDs, NEON codes or names (up to 20); for product='BIF', AA-Flx (sites "
        "with flux data) or AA-Net (all sites).",
    )
    product: str = Field(
        "BASE-BADM",
        description="BASE-BADM, FLUXNET (FLUXNET-1F, FULLSET) or BIF (bulk BADM). FLUXNET2015 "
        "and FLUXNET-CH4 come from fluxnet.org (ameriflux://guide/fluxnet2015-access).",
    )
    policy: str | None = Field(
        None,
        description="CCBY4.0 or LEGACY. Default: the policy the sites require (Legacy if any "
        "selected site is Legacy). FLUXNET is CC-BY-4.0 only.",
    )
    profile: str = Field(
        DEFAULT_PROFILE,
        pattern=r"^[A-Za-z0-9_.-]{1,64}$",
        description="Name of the configured identity profile (intended use and description).",
    )
    accept_data_policy: str | None = Field(
        None,
        description="With confirm=true: the policy code the plan showed (CCBY4.0 or LEGACY), "
        "meaning the user accepts it.",
    )
    confirm: bool = Field(
        False,
        description="false: return the plan only. true: send the request, only after the user "
        "approved the plan.",
    )
    if_exists: Literal["skip", "replace"] = Field(
        "skip",
        description="A file already downloaded: skip keeps it; replace fetches it again unless "
        "it is identical.",
    )


class SiteChoice(AmfOutput):
    site_id: str
    name: str | None = None
    policy: str | None = Field(None, description="The policy the site shares its data under.")
    years: str | None = Field(None, description="Published years under the request's policy.")


class IneligibleSite(AmfOutput):
    site_id: str
    reason: str


class DisclosureOut(AmfOutput):
    """The request body AmeriFlux receives, identity values masked."""

    sent_to: str
    recipients: list[str] = Field(description="Who AmeriFlux passes the request on to.")
    user_id: str
    user_email: str
    user_name: str | None = None
    intended_use: str | None = Field(None, description="Category, as AmeriFlux receives it.")
    description: str | None = Field(
        None, description="The user's own text, with ' [ameriflux-mcp]' appended."
    )
    site_ids: list[str]
    data_product: str
    data_variant: str | None = None
    data_policy: str
    is_test: bool | None = None


class IdentityOut(AmfOutput):
    configured: bool = Field(description="User ID and email are set (values never shown).")
    profile: str
    profile_complete: bool
    profiles: list[str]
    is_test_set: bool
    is_test: bool | None = None


class PolicyOut(AmfOutput):
    code: str
    reason: str
    obligations: list[ObligationOut]


class LocalCopy(AmfOutput):
    path: str
    site_id: str | None = None
    version: str | None = None
    bytes: int


class FileOut(AmfOutput):
    path: str
    name: str
    site_id: str | None = None
    status: Literal["downloaded", "skipped", "failed"]
    bytes: int | None = None
    sha256: str | None = None
    etag: str | None = None
    version: str | None = None
    reason: str | None = None
    error: str | None = None
    identical: bool | None = Field(
        None, description="For a kept file: whether it matches the server copy (null: unknown)."
    )


class SkippedLink(AmfOutput):
    name: str
    site_id: str | None = None
    reason: str
    text: str


class ManifestFile(AmfOutput):
    site_id: str | None = None
    filename: str | None = None
    start_year: str | None = None
    end_year: str | None = None
    version: str | None = None
    file_type: str | None = None
    timestamp: str | None = None


class ManifestOut(AmfOutput):
    path: str = Field(description="The manifest written next to the files (no identity).")
    download_timestamp: str | None = None
    number_of_sites_downloaded: int | None = None
    data_files: list[ManifestFile] = Field(default_factory=list)


class CitationRef(AmfOutput):
    site_id: str
    doi: str
    citation: str


class Totals(AmfOutput):
    files: int
    bytes: int
    seconds: float


class DownloadResult(ToolResultBase):
    mode: Literal["plan", "download"]
    product: str
    data_product: str = Field(description="The product AmeriFlux receives (BIF goes as BASE-BADM).")
    policy: PolicyOut
    eligible: list[SiteChoice]
    ineligible: list[IneligibleSite] = Field(default_factory=list)
    disclosure: DisclosureOut
    identity: IdentityOut
    ready: bool = Field(description="Whether confirm=true would send the request now.")
    blockers: list[str] = Field(default_factory=list, description="What must change first.")
    local_copies: list[LocalCopy] = Field(default_factory=list)
    download_dir: str
    files: list[FileOut] = Field(default_factory=list)
    skipped: list[SkippedLink] = Field(default_factory=list)
    manifest: ManifestOut | None = None
    pi_contact_count: int | None = Field(
        None, description="PI contact emails AmeriFlux returned (never stored or shown)."
    )
    citations: list[CitationRef] = Field(default_factory=list)
    totals: Totals | None = None


# ---------------------------------------------------------------------- helpers


def _client(ctx: ToolContext) -> AmeriFluxClient:
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise ToolError("internal_error", "No upstream client is configured.")
    return ctx.client


def _bulk_ids(values: Sequence[str]) -> list[str] | None:
    """``['aa-flx']`` -> ``['AA-Flx']``; ``None`` when any value is not a bulk ID."""
    canonical = {s.upper(): s for s in BULK_SITES}
    out = [canonical.get(v.strip().upper()) for v in values]
    return None if any(v is None for v in out) else list(dict.fromkeys(v for v in out if v))


def _policy(
    product: Product, records: Sequence[SiteRecord], requested: Policy | None
) -> tuple[Policy, str, dict[str, str]]:
    """The policy sent upstream, why, and the sites it rules out."""
    if product == "BIF":
        code: Policy = requested or "CCBY4.0"
        why = (
            f"{code} was requested"
            if requested
            else "CC-BY-4.0 by default; pass policy='LEGACY' for the Legacy BADM as well"
        )
        return code, why, {}
    if product == "BASE-BADM" and requested == "CCBY4.0":
        ruled_out = {
            r.site_id: "shares its data under the Legacy policy; request it with policy='LEGACY'"
            for r in records
            if r.policy == "LEGACY"
        }
        return "CCBY4.0", "CCBY4.0 was requested", ruled_out
    verdict = effective_policy(product, records, requested)
    return verdict.code, verdict.reason, dict(verdict.ineligible)


def _obligations(product: Product, code: Policy) -> list[ObligationOut]:
    items: list[Obligation] = obligations(info(product).collection, code, product)
    return [ObligationOut(text=o.text, level=o.level) for o in items]


def _identity(ctx: ToolContext, profile: str) -> tuple[IdentityOut, list[str], Identity | None]:
    status = identity_status(ctx.config, transport=ctx.transport)
    blockers: list[str] = []
    identity = ctx.identity
    if identity is None:
        missing = [
            n
            for n, ok in (
                ("user_id", status.user_id_configured),
                ("user_email", status.email_configured),
            )
            if not ok
        ]
        blockers.append(
            f"The download identity is incomplete ({', '.join(missing) or 'not set'}): the user "
            f"sets it in the server's environment; see {IDENTITY_GUIDE}."
        )
    chosen = identity.profile(profile) if identity is not None else None
    if profile not in status.profiles:
        blockers.append(
            f"No identity profile named {profile!r} is configured (profiles: "
            f"{', '.join(status.profiles) or 'none'})."
        )
    elif profile not in status.complete_profiles:
        blockers.append(
            f"Profile {profile!r} needs both an intended use and a description written by the "
            "user (AMERIFLUX_INTENDED_USE, AMERIFLUX_DESCRIPTION)."
        )
    if not status.is_test_set:
        blockers.append(
            "AMERIFLUX_MCP_IDENTITY__IS_TEST is not set: the user chooses true (test request) or "
            "false (real download); there is no default."
        )
    out = IdentityOut(
        configured=status.configured,
        profile=profile,
        profile_complete=chosen is not None and chosen.complete,
        profiles=status.profiles,
        is_test_set=status.is_test_set,
        is_test=status.is_test,
    )
    return out, blockers, identity


def _require_identity(ctx: ToolContext, identity: Identity | None, profile: str) -> Identity:
    """auth_required unless the identity, the profile and is_test are all set (D12, D17)."""
    status = identity_status(ctx.config, transport=ctx.transport)
    if identity is None:
        missing = [
            n
            for n, ok in (
                ("user_id", status.user_id_configured),
                ("user_email", status.email_configured),
            )
            if not ok
        ]
        raise identity_required_error(
            tool=ctx.tool_name, reason="identity_missing", missing=missing
        )
    chosen = identity.profile(profile)
    if chosen is None:
        error = identity_required_error(tool=ctx.tool_name, reason="profile_missing")
        error.details["profiles"] = status.profiles
        raise error
    if not chosen.complete:
        missing = [
            n
            for n, v in (("intended_use", chosen.intended_use), ("description", chosen.description))
            if v is None
        ]
        raise identity_required_error(
            tool=ctx.tool_name, reason="profile_incomplete", missing=missing
        )
    if identity.is_test is None:
        raise identity_required_error(
            tool=ctx.tool_name, reason="is_test_unset", missing=["is_test"]
        )
    return identity


def _disclosure(
    identity: Identity | None,
    chosen: Profile | None,
    *,
    site_ids: list[str],
    data_product: str,
    data_variant: str | None,
    code: Policy,
) -> DisclosureOut:
    return DisclosureOut(
        sent_to=SENT_TO,
        recipients=list(RECIPIENTS),
        user_id=MASKED if identity is not None else MISSING,
        user_email=MASKED if identity is not None else MISSING,
        user_name=MASKED if identity is not None and identity.user_name else None,
        intended_use=chosen.intended_use_label() if chosen else None,
        description=chosen.tagged_description() if chosen else None,
        site_ids=site_ids,
        data_product=data_product,
        data_variant=data_variant,
        data_policy=code,
        is_test=identity.is_test if identity is not None else None,
    )


def _body(
    identity: Identity,
    profile: str,
    *,
    site_ids: list[str],
    data_product: str,
    data_variant: str | None,
    code: Policy,
) -> dict[str, Any]:
    """The request body (D11, D12): the only place identity values are read."""
    chosen = identity.profile(profile)
    if chosen is None or not chosen.complete:  # pragma: no cover - _require_identity checked
        raise identity_required_error(tool="amf_download_data", reason="profile_incomplete")
    body: dict[str, Any] = {
        "user_id": identity.user_id,
        "user_email": identity.user_email,
        "site_ids": site_ids,
        "data_product": data_product,
        "data_policy": code,
        "intended_use": chosen.intended_use_label(),
        "description": chosen.tagged_description(),
        "is_test": bool(identity.is_test),
    }
    if data_variant:
        body["data_variant"] = data_variant
    if identity.user_name:
        body["user_name"] = identity.user_name
    return body


def _local_copies(ctx: ToolContext, product: Product, site_ids: Sequence[str]) -> list[LocalCopy]:
    root = ctx.config.downloads.directory
    if not root.is_dir():
        return []
    wanted = {s.upper() for s in site_ids}
    found = [
        f
        for f in walk([(root, root)]).found
        if f.name.product == product
        and (f.name.is_archive or product == "BIF")
        and (f.name.site_id or "").upper() in wanted
    ]
    found.sort(key=lambda f: ((f.name.site_id or "").upper(), version_key(f.name)), reverse=True)
    return [
        LocalCopy(
            path=str(f.path),
            site_id=f.name.site_id,
            version=f.name.version or f.name.date,
            bytes=f.size,
        )
        for f in found[:20]
    ]


def _drift(detail: str, missing: list[str]) -> AmeriFluxApiError:
    return AmeriFluxApiError(
        200,
        detail,
        "POST amfcdn.lbl.gov/api/v1/data_download",
        kind="drift",
        missing=missing,
        identity_sent=True,
    )


def _parse_response(payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any], int | None]:
    """``data_urls``, the manifest (emails removed) and the PI-contact count (D19)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data_urls"), list):
        raise _drift("the response has no data_urls list", ["data_urls"])
    links = [link for link in payload["data_urls"] if isinstance(link, dict)]
    manifest = payload.get("manifest")
    manifest = strip_emails(manifest) if isinstance(manifest, dict) else {}
    contacts = payload.get("pi_contact_emails")
    count = len(contacts) if isinstance(contacts, list) else None
    return links, manifest, count


def _manifest_files(manifest: dict[str, Any]) -> list[ManifestFile]:
    rows = manifest.get("data_files")
    out: list[ManifestFile] = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            values = {k: (None if row.get(k) is None else str(row.get(k))) for k in MANIFEST_KEYS}
            out.append(ManifestFile(**values))
    return out


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


async def _citations(
    ctx: ToolContext, product: Product, records: Sequence[SiteRecord], notes: list[str]
) -> dict[str, CitationRef]:
    if product == "BIF":
        notes.append(
            "Bulk BADM has no DOI of its own; cite each site you use with its BASE-BADM DOI "
            "(amf_get_citation(product='BIF'))."
        )
        return {}
    out: dict[str, CitationRef] = {}
    failed: list[str] = []
    for record in records:
        try:
            cited = await _cite_one(ctx, record, product)  # type: ignore[arg-type]
        except (AmeriFluxApiError, ToolError):
            failed.append(record.site_id)
            continue
        if isinstance(cited, str):
            failed.append(record.site_id)
            continue
        out[record.site_id.upper()] = CitationRef(
            site_id=record.site_id, doi=cited.doi, citation=cited.text
        )
    if failed:
        notes.append(
            f"No citation could be fetched for {', '.join(failed)} now; call amf_get_citation "
            "later."
        )
    return out


def _version(file_name: str) -> str | None:
    name = classify(file_name)
    return (name.version or name.date) if name else None


def _file_out(outcome: Outcome, version: str | None) -> FileOut:
    return FileOut(
        path=str(outcome.path),
        name=outcome.entry.name,
        site_id=outcome.entry.site_id or None,
        status=outcome.status,
        bytes=outcome.bytes,
        sha256=outcome.sha256,
        etag=outcome.etag,
        version=version,
        reason=outcome.reason,
        error=outcome.error,
        identical=outcome.identical,
    )


# ---------------------------------------------------------------------- the tool


@register_tool(
    "amf_download_data",
    title="Download AmeriFlux data (with consent)",
    description=(
        "Download AmeriFlux BASE-BADM, FLUXNET (FULLSET) or bulk BADM (BIF: AA-Flx/AA-Net) "
        "through AmeriFlux's logged route; stdio only. confirm=false (default) returns a plan: "
        "the exact text sent to the site PIs and the download log, eligible sites and the data "
        "policy; nothing is sent. Only after the user approves it, call again with confirm=true "
        "and accept_data_policy set to the plan's policy. Files are verified (size, ETag, zip "
        "CRC; sha256 sidecar). Next: amf_preview_data on a downloaded file."
    ),
    input_model=DownloadIn,
    output_model=DownloadResult,
    surface="data",
    endpoints=DOWNLOAD_ENDPOINTS,
    requires_key=True,
    key_check="handler",
    transports=("stdio",),
    read_only=False,
    destructive=False,
    idempotent=False,
    open_world=True,
    needs_downloads=True,
)
async def amf_download_data(args: DownloadIn, ctx: ToolContext) -> DownloadResult:
    if ctx.transport != "stdio":
        raise ToolError(
            "not_available_in_http_mode",
            "Downloads act with the user's identity and write to their disk: stdio only.",
        )
    if not ctx.config.effective_downloads_enabled(ctx.transport):
        raise ToolError("feature_unavailable", "Downloads are disabled (downloads.enabled=false).")
    started = time.monotonic()
    product = normalize_product(args.product)
    bulk = _bulk_ids(args.sites) if product == "BIF" else None
    request = download_request(product, bulk if bulk is not None else args.sites)
    requested = normalize_policy(args.policy, field="policy") if args.policy else None
    if requested is not None:
        validate(product, requested)

    notes: list[str] = []
    resolved = []
    records: list[SiteRecord] = []
    if bulk is None:
        index = await site_index(ctx)
        resolutions = resolve_sites(args.sites, index)
        records = [r.record for r in resolutions]
        resolved = [r.resolved for r in resolutions if r.resolved]
        for r in resolutions:
            notes.extend(r.notes)

    code, why, ruled_out = _policy(product, records, requested)
    eligible: list[SiteChoice] = []
    ineligible = [IneligibleSite(site_id=s, reason=r) for s, r in ruled_out.items()]
    chosen_records: list[SiteRecord] = []
    if bulk is not None:
        eligible = [SiteChoice(site_id=s) for s in bulk]
    else:
        years = await _read_years(ctx, product, code)
        for record in records:
            if record.site_id in ruled_out:
                continue
            site_years = years.get(record.site_id)
            if site_years:
                eligible.append(
                    SiteChoice(
                        site_id=record.site_id,
                        name=record.name,
                        policy=record.policy,
                        years=compact_years(site_years),
                    )
                )
                chosen_records.append(record)
            else:
                ineligible.append(
                    IneligibleSite(
                        site_id=record.site_id, reason=_empty_reason(record, product, code)
                    )
                )
    site_ids = [s.site_id for s in eligible]
    policy_out = PolicyOut(code=code, reason=why, obligations=_obligations(product, code))
    identity_out, blockers, identity = _identity(ctx, args.profile)
    if not eligible:
        blockers.insert(0, f"No requested site has {product} data under {code}.")
    disclosure = _disclosure(
        identity,
        configured_profile(ctx.config, args.profile),
        site_ids=site_ids,
        data_product=request.data_product,
        data_variant=request.data_variant,
        code=code,
    )
    root = ctx.config.downloads.directory
    common: dict[str, Any] = {
        "product": product,
        "data_product": request.data_product,
        "policy": policy_out,
        "eligible": eligible,
        "ineligible": ineligible,
        "disclosure": disclosure,
        "identity": identity_out,
        "download_dir": str(root),
        "resolved": resolved,
    }
    if product == "BIF":
        notes.append(
            "Bulk BADM is requested as BASE-BADM for "
            f"{', '.join(site_ids)} (as amerifluxr does); FLUXNET-BIF links are not downloaded."
        )

    if not args.confirm:
        copies = _local_copies(ctx, product, site_ids)
        if copies:
            notes.append(
                f"{len(copies)} matching file(s) are already in the download directory; a new "
                "request still notifies the PIs. Read them with amf_preview_data instead if "
                "they are current."
            )
        steps: list[str]
        if blockers:
            steps = [
                f"Ask the user to fix: {blockers[0]} Do not write the intended use or "
                f"description for them (read {IDENTITY_GUIDE}).",
            ]
        else:
            steps = [
                "Show the user the disclosure (what AmeriFlux sends to the site PIs) and the "
                "policy obligations, and ask whether to proceed.",
                "Only if they agree: amf_download_data("
                f"sites={site_ids!r}, product={product!r}"
                + (f", profile={args.profile!r}" if args.profile != DEFAULT_PROFILE else "")
                + (f", policy={requested!r}" if requested else "")
                + f", accept_data_policy={code!r}, confirm=true)",
            ]
        notes.append("Plan only: nothing was sent to AmeriFlux.")
        return DownloadResult(
            mode="plan",
            ready=not blockers,
            blockers=blockers,
            local_copies=copies,
            notes=merge_notes(notes),
            next_steps=steps,
            source=source(ctx),
            **common,
        )

    # ------------------------------------------------------------ confirmed
    if args.accept_data_policy is None:
        raise ToolError(
            "invalid_argument",
            f"confirm=true needs accept_data_policy='{code}': the user must accept the data "
            "policy these sites are shared under.",
            details={"reason": "policy_not_accepted", "effectivePolicy": code},
            hint="Call with confirm=false to show the user the plan first.",
        )
    accepted = normalize_policy(args.accept_data_policy, field="accept_data_policy")
    if accepted != code:
        raise ToolError(
            "invalid_argument",
            f"accept_data_policy is {accepted}, but this request falls under {code} ({why}).",
            details={"reason": "policy_mismatch", "effectivePolicy": code, "accepted": accepted},
            hint="Show the user the plan again; they accept the policy the plan names.",
        )
    identity = _require_identity(ctx, identity, args.profile)
    if not eligible:
        raise ToolError(
            "not_found",
            f"No requested site has {product} data under {code}; nothing was sent.",
            details={
                "reason": "no_eligible_sites",
                "ineligible": [s.model_dump(by_alias=True) for s in ineligible],
            },
        )

    client = _client(ctx)
    request_id = uuid.uuid4().hex[:12]
    payload = await client.post_download(
        _body(
            identity,
            args.profile,
            site_ids=site_ids,
            data_product=request.data_product,
            data_variant=request.data_variant,
            code=code,
        ),
        stats=ctx.stats,
    )
    ctx.log.info("download.requested", request_id=request_id, product=product, sites=len(site_ids))
    links, manifest, contacts = _parse_response(payload)
    entries, link_skips = client.ledger.record(
        links,
        request_id=request_id,
        product=product,
        policy=code,
        requested_sites=site_ids,
        check=client.check_download_link,
    )
    citations = await _citations(ctx, product, chosen_records, notes)

    manager = DownloadManager(
        ctx.config.downloads, client, zip_member_max_bytes=ctx.config.limits.zip_member_max_bytes
    )
    config = ctx.config.downloads
    outcomes: list[Outcome] = []
    skipped: list[Skipped] = list(link_skips)
    planned_bytes = 0
    transferred = 0
    free = manager.free_bytes()
    for entry in entries:
        path = manager.destination(entry)
        try:
            head = await manager.head(entry, stats=ctx.stats)
        except ToolError as exc:
            outcomes.append(
                Outcome(
                    entry,
                    path,
                    "failed",
                    reason=str(exc.details.get("reason") or exc.code),
                    error=f"{exc.code}: {exc.message}",
                )
            )
            continue
        identical = manager.existing(entry, path, head)
        if path.exists() and (args.if_exists == "skip" or identical is True):
            outcomes.append(
                Outcome(
                    entry,
                    path,
                    "skipped",
                    bytes=path.stat().st_size,
                    reason="exists",
                    identical=identical,
                )
            )
            if identical is False:
                notes.append(
                    f"{entry.name} differs from the server copy; pass if_exists='replace' to "
                    "fetch it again."
                )
            continue
        size = head.length
        if size is not None and size > config.max_file_bytes:
            outcomes.append(
                Outcome(
                    entry,
                    path,
                    "failed",
                    reason="over_file_limit",
                    error=f"download_limit_exceeded: {size} bytes is above "
                    f"downloads.max_file_bytes ({config.max_file_bytes}).",
                )
            )
            continue
        if transferred >= config.max_files_per_call or (
            size is not None and planned_bytes + size > config.max_bytes_per_call
        ):
            reason = (
                "call_file_limit" if transferred >= config.max_files_per_call else "call_byte_limit"
            )
            outcomes.append(Outcome(entry, path, "skipped", reason=reason))
            continue
        if free is not None and size is not None and size + DISK_MARGIN_BYTES > free:
            outcomes.append(
                Outcome(
                    entry,
                    path,
                    "failed",
                    reason="disk_full",
                    error="download_limit_exceeded: not enough free disk space.",
                )
            )
            continue
        planned_bytes += size or 0
        transferred += 1
        outcome = await manager.fetch(
            entry,
            path,
            head,
            stats=ctx.stats,
            sidecar={
                "version": _version(entry.name),
                "isTest": bool(identity.is_test),
                "citation": (
                    citations[entry.site_id.upper()].model_dump(by_alias=True)
                    if entry.site_id.upper() in citations
                    else None
                ),
                "obligations": [o.model_dump(by_alias=True) for o in policy_out.obligations],
            },
        )
        if free is not None and outcome.bytes:
            free -= outcome.bytes
        outcomes.append(outcome)

    stamp = utc_now()
    files = [_file_out(o, _version(o.entry.name)) for o in outcomes]
    for o in outcomes:
        notes.extend(o.notes)
    manifest_rows = _manifest_files(manifest)
    mpath = manifest_path(root, product, stamp)
    write_json(
        mpath,
        {
            "schema": MANIFEST_SCHEMA,
            "requestId": request_id,
            "requestedAt": stamp,
            "tool": "amf_download_data",
            "request": {
                "siteIds": site_ids,
                "product": product,
                "dataProduct": request.data_product,
                "dataVariant": request.data_variant,
                "dataPolicy": code,
                "profile": args.profile,
                "intendedUse": disclosure.intended_use,
                "isTest": bool(identity.is_test),
            },
            "obligations": [o.model_dump(by_alias=True) for o in policy_out.obligations],
            "files": [f.model_dump(by_alias=True, exclude_none=True) for f in files],
            "skipped": [{"name": s.name, "siteId": s.site_id, "reason": s.reason} for s in skipped],
            "upstreamManifest": {
                "downloadTimestamp": manifest.get("download_timestamp"),
                "numberOfSitesDownloaded": manifest.get("number_of_sites_downloaded"),
                "dataFiles": [
                    m.model_dump(by_alias=True, exclude_none=True) for m in manifest_rows
                ],
            },
            "citations": [c.model_dump(by_alias=True) for c in citations.values()],
        },
    )

    downloaded = [o for o in outcomes if o.status == "downloaded"]
    failed = [o for o in outcomes if o.status == "failed"]
    limited = [o for o in outcomes if o.reason in ("call_file_limit", "call_byte_limit")]
    if not links:
        notes.append(
            f"AmeriFlux returned no files for {', '.join(site_ids)} under {code}; the request "
            "was still logged."
        )
    if failed:
        notes.append(f"{len(failed)} file(s) failed; see files[].error. Nothing partial was kept.")
    if limited:
        notes.append(
            f"{len(limited)} file(s) were not fetched because of the per-call limits "
            "(downloads.max_files_per_call, downloads.max_bytes_per_call)."
        )
    if contacts:
        notes.append(
            f"AmeriFlux returned {contacts} PI contact email(s); they are not stored or shown. "
            "Site team contacts are on each site's AmeriFlux page."
        )
    if bool(identity.is_test):
        notes.append("Sent as a test request (identity.is_test=true).")
    steps = [f"amf_preview_data(file={str(o.path)!r})" for o in downloaded[:1]] + [
        f"amf_get_citation(sites={site_ids!r}, product={product!r}) for the reference list",
    ]
    if downloaded and product != "BIF":
        steps.insert(1, f"amf_read_bif(file={str(downloaded[0].path)!r}) for the site metadata")
    return DownloadResult(
        mode="download",
        ready=True,
        files=files,
        skipped=[
            SkippedLink(name=s.name, site_id=s.site_id, reason=s.reason, text=s.text)
            for s in skipped
        ],
        manifest=ManifestOut(
            path=str(mpath),
            download_timestamp=None
            if manifest.get("download_timestamp") is None
            else str(manifest.get("download_timestamp")),
            number_of_sites_downloaded=_as_int(manifest.get("number_of_sites_downloaded")),
            data_files=manifest_rows,
        ),
        pi_contact_count=contacts,
        citations=list(citations.values()),
        totals=Totals(
            files=len(downloaded),
            bytes=sum(o.bytes or 0 for o in downloaded),
            seconds=round(time.monotonic() - started, 3),
        ),
        notes=merge_notes(notes),
        next_steps=steps,
        source=source(ctx),
        **common,
    )


__all__ = ["DownloadIn", "DownloadResult", "amf_download_data"]
