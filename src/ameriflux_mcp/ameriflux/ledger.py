"""The URL ledger: files ameriflux-mcp may fetch (DESIGN.md D15).

A data file is fetched only if its URL came back from a logged ``data_download``
request in this process. :meth:`Ledger.record` classifies each returned link
(allow-listed host and path, a safe file name, a requested site, not a
``FLUXNET-BIF`` link) and keeps the ones that pass; :meth:`Ledger.require` is the
gate the download manager goes through before any HEAD or GET.

URLs are stored with their ``?=<user_id>`` tag stripped (the tag is the only part
of a file URL that names the user; RESEARCH.md E23 shows the file is the same
without it), so the ledger holds no identity and every request to the file
server carries none. Nothing here is written to disk.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from ameriflux_mcp.errors import ToolError

#: File names written to disk: letters, digits, '.', '_', '-' (no separators).
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SkipReason = Literal["fluxnet_bif", "off_allow_list", "unsafe_name", "not_requested", "duplicate"]
SKIP_TEXT: dict[str, str] = {
    "fluxnet_bif": "FLUXNET-BIF links are not downloaded (as amerifluxr; DESIGN.md D11)",
    "off_allow_list": "the link is outside ameriflux-mcp's file-server allow-list",
    "unsafe_name": "the file name is not a plain AmeriFlux file name",
    "not_requested": "the link is for a site that was not requested",
    "duplicate": "the same file was listed twice",
}


def canonical_url(url: str) -> str:
    """``url`` without its query and fragment (the ``?=<user_id>`` tag)."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def file_name(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class LedgerEntry:
    """One file a logged download request returned."""

    url: str
    name: str
    site_id: str
    data_product: str
    product: str
    policy: str
    request_id: str
    download_size: int | None = None
    recorded_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Skipped:
    name: str
    site_id: str | None
    reason: SkipReason

    @property
    def text(self) -> str:
        return SKIP_TEXT[self.reason]


def _size(value: Any) -> int | None:
    try:
        size = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


class Ledger:
    """Process-wide record of the URLs ``data_download`` handed out."""

    def __init__(self, *, max_entries: int = 5000) -> None:
        self._entries: dict[str, LedgerEntry] = {}
        self._max = max_entries

    def __len__(self) -> int:
        return len(self._entries)

    def record(
        self,
        links: Iterable[Mapping[str, Any]],
        *,
        request_id: str,
        product: str,
        policy: str,
        requested_sites: Iterable[str],
        check: Callable[[str], None],
    ) -> tuple[list[LedgerEntry], list[Skipped]]:
        """Admit the links of one response; ``check`` is the client's allow-list test."""
        wanted = {s.upper() for s in requested_sites}
        kept: list[LedgerEntry] = []
        skipped: list[Skipped] = []
        seen: set[str] = set()
        for link in links:
            raw = str(link.get("url") or "")
            url = canonical_url(raw)
            name = file_name(url)
            site = str(link.get("site_id") or "").strip() or None
            data_product = str(link.get("data_product") or "")
            reason: SkipReason | None = None
            if "FLUXNET-BIF" in data_product.upper() or "FLUXNET-BIF" in url.upper():
                reason = "fluxnet_bif"
            elif not NAME_RE.match(name):
                reason = "unsafe_name"
            else:
                try:
                    check(url)
                except ToolError:
                    reason = "off_allow_list"
            if reason is None and site is not None and site.upper() not in wanted:
                reason = "not_requested"
            if reason is None and url in seen:
                reason = "duplicate"
            if reason is not None:
                skipped.append(Skipped(name or raw[:80], site, reason))
                continue
            seen.add(url)
            entry = LedgerEntry(
                url=url,
                name=name,
                site_id=site or "",
                data_product=data_product,
                product=product,
                policy=policy,
                request_id=request_id,
                download_size=_size(link.get("download_size")),
            )
            self._entries[url] = entry
            kept.append(entry)
        while len(self._entries) > self._max:
            self._entries.pop(next(iter(self._entries)))
        return kept, skipped

    def require(self, url: str) -> LedgerEntry:
        """The entry for ``url``, or ``download_denied``: only logged URLs are fetched."""
        entry = self._entries.get(canonical_url(url))
        if entry is None:
            raise ToolError(
                "download_denied",
                "This URL did not come from an AmeriFlux download request in this session, so "
                "it is not fetched (DESIGN.md D15).",
                details={"reason": "not_in_ledger", "name": file_name(url)},
                hint="Call amf_download_data, which requests the files through AmeriFlux's "
                "logged route.",
            )
        return entry


__all__ = [
    "NAME_RE",
    "SKIP_TEXT",
    "Ledger",
    "LedgerEntry",
    "SkipReason",
    "Skipped",
    "canonical_url",
    "file_name",
]
