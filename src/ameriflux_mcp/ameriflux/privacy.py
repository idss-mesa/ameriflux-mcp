"""Personal data in upstream responses (DESIGN.md D19).

The AmeriFlux site catalog lists every team member's email, and DOI records list
every contributor's. ameriflux-mcp returns names, roles and institutions by default
and emails only when a call asks for contacts **and** the operator enabled
``privacy.allow_contact_emails``. Emails never reach the disk cache, logs, download
records or test fixtures: :func:`strip_emails` is applied before anything is
written.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ameriflux_mcp.config import Config

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EMAIL_KEY = re.compile(r"(?i)e-?mail")

CONTACTS_WITHHELD_NOTE = (
    "Contact emails are withheld (privacy.allow_contact_emails is off on this server); names, "
    "roles and institutions are shown. Site pages on ameriflux.lbl.gov list contacts."
)


def strip_emails(value: Any) -> Any:
    """A copy without email-named keys and with email-shaped strings replaced."""
    if isinstance(value, dict):
        return {
            k: strip_emails(v)
            for k, v in value.items()
            if not (isinstance(k, str) and _EMAIL_KEY.search(k))
        }
    if isinstance(value, list):
        return [strip_emails(v) for v in value]
    if isinstance(value, str) and "@" in value:
        return EMAIL_RE.sub("[email withheld]", value)
    return value


def contacts_allowed(config: Config, include_contacts: bool) -> bool:
    """Both the caller and the operator must opt in."""
    return include_contacts and config.privacy.allow_contact_emails


__all__ = ["CONTACTS_WITHHELD_NOTE", "EMAIL_RE", "contacts_allowed", "strip_emails"]
