from __future__ import annotations

import httpx
import pytest

from ameriflux_mcp.ameriflux.client import AmeriFluxClient, endpoint_label, user_agent
from ameriflux_mcp.config import UpstreamConfig
from ameriflux_mcp.context import UpstreamStats
from ameriflux_mcp.errors import AmeriFluxApiError
from tests.upstream_stub import UpstreamStub


@pytest.fixture
async def client(stub: UpstreamStub) -> AmeriFluxClient:
    return AmeriFluxClient(UpstreamConfig(), http_transport=stub.transport)


def test_user_agent_and_labels() -> None:
    assert user_agent() == "ameriflux-mcp/0.1.0 (+https://github.com/idss-mesa/ameriflux-mcp)"
    assert user_agent("ci").endswith(" ci")
    assert (
        endpoint_label("GET", "https://amfcdn.lbl.gov/api/v1/fp_var?limits=True#x")
        == "GET amfcdn.lbl.gov/api/v1/fp_var"
    )


async def test_get_json_records_stats(client: AmeriFluxClient, stub: UpstreamStub) -> None:
    stats = UpstreamStats()
    body = await client.get_json("v1/fp_var", stats=stats)
    assert [v["Name"] for v in body] == ["FC", "TA"]
    assert stats.requests == 1 and stats.backend == "amfcdn"
    assert stats.endpoints == ["GET amfcdn.lbl.gov/api/v1/fp_var"]
    assert stub.calls[0].headers["accept"] == "application/json"
    await client.aclose()


async def test_refuses_other_hosts(client: AmeriFluxClient, stub: UpstreamStub) -> None:
    client.base_url = "https://example.org/api"
    with pytest.raises(ValueError, match="outside the AmeriFlux API"):
        await client.get_json("v1/fp_var", stats=UpstreamStats())
    assert stub.calls == []
    await client.aclose()


async def test_refuses_plain_http(stub: UpstreamStub) -> None:
    client = AmeriFluxClient(
        UpstreamConfig(api_base_url="http://amfcdn.lbl.gov/api"), http_transport=stub.transport
    )
    with pytest.raises(ValueError, match="non-https"):
        await client.get_json("v1/fp_var", stats=UpstreamStats())
    assert stub.calls == []
    await client.aclose()


async def test_http_errors_and_transport_failures(
    client: AmeriFluxClient, stub: UpstreamStub
) -> None:
    stub.answers["/api/v1/nope"] = (404, {"detail": {}, "message": "Not Found"})
    with pytest.raises(AmeriFluxApiError) as not_found:
        await client.get_json("v1/nope", stats=UpstreamStats())
    assert not_found.value.status == 404 and not_found.value.kind == "http"
    stub.inject(httpx.ReadTimeout)
    with pytest.raises(AmeriFluxApiError) as timeout:
        await client.get_json("v1/fp_var", stats=UpstreamStats())
    assert timeout.value.kind == "transport" and timeout.value.status == 0
    await client.aclose()


async def test_redirects_are_not_followed(client: AmeriFluxClient, stub: UpstreamStub) -> None:
    stub.answers["/api/v1/moved"] = (302, {})
    with pytest.raises(AmeriFluxApiError) as moved:
        await client.get_json("v1/moved", stats=UpstreamStats())
    assert moved.value.status == 302
    assert len(stub.calls) == 1
    await client.aclose()


async def test_byte_cap_and_decode_errors(stub: UpstreamStub) -> None:
    client = AmeriFluxClient(UpstreamConfig(max_response_bytes=1024), http_transport=stub.transport)
    stub.answers["/api/v1/big"] = (200, ["x" * 2000])
    with pytest.raises(AmeriFluxApiError) as big:
        await client.get_json("v1/big", stats=UpstreamStats())
    assert big.value.kind == "decode" and "cap" in big.value.detail
    await client.aclose()
