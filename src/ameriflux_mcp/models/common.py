"""Base models, the result envelope, and shared input types.

Naming (neon-mcp D1, kept): input fields are snake_case in every
``inputSchema`` and also accept the camelCase spelling; output keys are
camelCase, including ameriflux-mcp's additions (``nextSteps``, ``page.nextOffset``,
``siteId``).
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import (
    AliasChoices,
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic.alias_generators import to_camel


def _validation_alias(name: str) -> AliasChoices:
    camel = to_camel(name)
    return AliasChoices(name, camel) if camel != name else AliasChoices(name)


class AmfInput(BaseModel):
    """Base for every tool input: snake_case advertised, camelCase accepted, extras rejected."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        alias_generator=AliasGenerator(validation_alias=_validation_alias),
    )


class AmfOutput(BaseModel):
    """Base for every output object; dumped ``by_alias`` so keys are camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    #: Name of the list field :func:`ameriflux_mcp.registry.fit_to_budget` may shorten.
    budget_list: ClassVar[str | None] = None
    #: Item fields nulled (from the tail) before items are dropped.
    budget_elide_fields: ClassVar[tuple[str, ...]] = ()
    #: Flag set on the payload when elision happened (e.g. ``urls_elided``).
    budget_elide_flag: ClassVar[str | None] = None
    #: The Page field describing ``budget_list``.
    budget_page: ClassVar[str] = "page"
    #: Next step added when ``budget_list`` is trimmed, for tools without offset/limit;
    #: ``{next_offset}`` is filled in. ``None`` = "call again with offset=…".
    budget_next_step: ClassVar[str | None] = None
    #: A boolean output field set to false when ``budget_list`` is trimmed (e.g. ``complete``).
    budget_incomplete_flag: ClassVar[str | None] = None


class Page(AmfOutput):
    """Pagination state of one list in a result."""

    total: int | None = Field(None, description="Total items available, when known.")
    returned: int = Field(description="Items in this result.")
    offset: int = Field(description="Offset of the first returned item.")
    limit: int = Field(description="Page size that was applied.")
    truncated: bool = Field(description="True when more items exist beyond this page.")
    next_offset: int | None = Field(
        None, description="Pass as offset to get the next page; absent when there is none."
    )
    truncated_reason: Literal["limit", "budget"] | None = Field(
        None,
        description="'limit' = page size reached; 'budget' = trimmed to the result-size budget.",
    )


class Resolved(AmfOutput):
    """Echo of an input normalized or fuzzy-resolved to an AmeriFlux or FLUXNET identifier."""

    field: str
    input: str
    code: str
    confidence: float


#: DESIGN.md D5: who answered. amfcdn = the AmeriFlux API, fluxdata = ftp.fluxdata.org files.
Backend = Literal["amfcdn", "fluxdata", "amerifluxr", "datacite", "local", "mixed"]


class Source(AmfOutput):
    """Where a result came from."""

    endpoints: list[str] = Field(
        default_factory=list,
        description="Upstream endpoints called (method, host and path; never a query or credential).",
    )
    backend: Backend = Field(
        "local",
        description="amfcdn (the AmeriFlux API), fluxdata (AmeriFlux file server), amerifluxr "
        "(dated coverage snapshots), datacite (DOI metadata), local (no upstream call) or mixed.",
    )
    cached: bool = False
    derived: list[str] = Field(
        default_factory=list,
        description="Fields computed by ameriflux-mcp rather than returned upstream.",
    )


class ToolResultBase(AmfOutput):
    """Envelope carried by every tool result."""

    resolved: list[Resolved] = Field(
        default_factory=list, description="Inputs normalized or resolved to site or product codes."
    )
    notes: list[str] = Field(
        default_factory=list, description="Caveats: policy, data gaps, snapshots, fallbacks used."
    )
    next_steps: list[str] = Field(default_factory=list, description="Concrete follow-up calls.")
    source: Source | None = None
