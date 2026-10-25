"""Tool families. Importing this package registers every tool."""

from ameriflux_mcp.tools import (  # noqa: F401  (registration side effects)
    availability,
    badm,
    citation,
    core,
    download,
    local,
    sites,
    variables,
)
