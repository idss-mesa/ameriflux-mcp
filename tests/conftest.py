"""Shared fixtures: config, server factory, secret isolation.

Unit tests never touch the network: every server built here talks to an
:class:`~tests.upstream_stub.UpstreamStub`, which answers the few API paths build
step 2 uses and fails the test on any other request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from ameriflux_mcp.config import Config, load_config
from ameriflux_mcp.logging import forget_secrets
from ameriflux_mcp.server import AmeriFluxServer, create_server
from tests.helpers import IDENTITY_ENV
from tests.upstream_stub import UpstreamStub


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    yield
    forget_secrets()


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config.model_validate(
        {
            "downloads": {"directory": str(tmp_path / "downloads")},
            "cache": {"disk_dir": str(tmp_path / "cache")},
        }
    )


@pytest.fixture
def identity_config(config: Config) -> Config:
    """``config`` plus the complete test identity, loaded the way the CLI loads it."""
    loaded = load_config(env=IDENTITY_ENV)
    cfg = config.model_copy(deep=True)
    cfg.identity = loaded.identity
    return cfg


@pytest.fixture
def stub() -> UpstreamStub:
    return UpstreamStub()


@pytest.fixture
async def make_server(
    config: Config, identity_config: Config, stub: UpstreamStub
) -> AsyncIterator[Callable[..., AmeriFluxServer]]:
    servers: list[AmeriFluxServer] = []

    def _make(
        *,
        transport: str = "stdio",
        identity: bool = False,
        config: Config | None = None,
        **_: Any,
    ) -> AmeriFluxServer:
        base = config or (identity_config if identity else _base)
        server = create_server(
            base.model_copy(deep=True),
            transport=transport,  # type: ignore[arg-type]
            http_transport=stub.transport,
        )
        servers.append(server)
        return server

    _base = config
    yield _make
    for server in servers:
        await server.aclose()


@pytest.fixture
async def server(make_server: Callable[..., AmeriFluxServer]) -> AmeriFluxServer:
    return make_server()


@pytest.fixture
async def identity_server(make_server: Callable[..., AmeriFluxServer]) -> AmeriFluxServer:
    return make_server(identity=True)


@pytest.fixture
async def http_server(make_server: Callable[..., AmeriFluxServer]) -> AmeriFluxServer:
    return make_server(transport="http")
