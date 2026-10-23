from __future__ import annotations

import pytest

from ameriflux_mcp.ameriflux.endpoints import (
    DATA_AVAILABILITY,
    DOI,
    FLUXNET_SITES,
    FP_VAR,
    SITE_AVAILABILITY,
    SITE_INFO,
)
from ameriflux_mcp.ameriflux.privacy import contacts_allowed, strip_emails
from ameriflux_mcp.config import Config
from ameriflux_mcp.errors import AmeriFluxApiError

LABEL = "GET amfcdn.lbl.gov/api/v1/x"


def test_strip_emails_removes_keys_and_scrubs_values() -> None:
    data = {
        "grp_team_member": [
            {"team_member_name": "A", "team_member_email": "a@example.net"},
            {"team_member_name": "B", "TEAM_MEMBER_EMAIL": "b@example.net"},
        ],
        "DOI_CONTRIBUTOR": [{"DOI_CONTRIBUTOR_EMAIL": "c@example.net", "note": "write to d@example.net"}],
        "count": 3,
    }
    clean = strip_emails(data)
    assert "@" not in str(clean)
    assert clean["grp_team_member"][0] == {"team_member_name": "A"}
    assert clean["DOI_CONTRIBUTOR"][0]["note"] == "write to [email withheld]"
    assert clean["count"] == 3 and "@" in str(data)  # the input is not modified


def test_contacts_need_both_flags() -> None:
    off = Config()
    on = Config.model_validate({"privacy": {"allow_contact_emails": True}})
    assert not contacts_allowed(off, True)
    assert not contacts_allowed(on, False)
    assert contacts_allowed(on, True)


def test_endpoint_paths_and_families() -> None:
    assert SITE_INFO.path() == "v2/site_info_display/AmeriFlux"
    assert FLUXNET_SITES.path(product="FLUXNET2015") == "v1/site_display/FLUXNET/FLUXNET2015"
    assert DOI.path(site="US-Ha1", product="FLUXNET") == "v1/DOI/US-Ha1/FLUXNET"
    assert FP_VAR.query == {"limits": "True"}
    assert DATA_AVAILABILITY.family_for(network="AmeriFlux") == "availability"
    assert DATA_AVAILABILITY.family_for(network="FLUXNET") == "fluxnet2015"
    assert SITE_INFO.family == "catalog" and DOI.family == "citations"


def test_unwrap_envelopes() -> None:
    assert SITE_INFO.version == "v2" and SITE_INFO.envelope == "values"
    row = {k: 1 for k in SITE_INFO.required}
    from ameriflux_mcp.ameriflux.endpoints import unwrap

    assert unwrap(SITE_INFO, {"values": [row]}, LABEL) == [row]
    assert unwrap(SITE_AVAILABILITY, {"AmeriFlux": {}, "FLUXNET": {}}, LABEL) == {
        "AmeriFlux": {},
        "FLUXNET": {},
    }
    avail = [{"SITE_ID": "US-Ha1", "publish_years": []}]
    assert unwrap(DATA_AVAILABILITY, avail, LABEL) == avail


@pytest.mark.parametrize("payload", [{}, {"status": "No valid DOI for BASE"}])
def test_doi_sentinels_are_none(payload: dict[str, str]) -> None:
    from ameriflux_mcp.ameriflux.endpoints import unwrap

    assert unwrap(DOI, payload, LABEL) is None


@pytest.mark.parametrize(
    ("endpoint", "payload", "missing"),
    [
        (SITE_INFO, [{"site_id": "x"}], ["values"]),  # v2 envelope lost
        (DATA_AVAILABILITY, {"values": []}, []),  # wrapped where bare is expected
        (DATA_AVAILABILITY, [{"SITE_ID": "US-Ha1"}], ["publish_years"]),
        (DOI, {"DOI_INFO": {}}, ["DOI_CONTRIBUTOR", "REFERENCES"]),
        (DOI, ["not", "an", "object"], []),
        (FP_VAR, ["FC"], []),
    ],
)
def test_drift(endpoint: object, payload: object, missing: list[str]) -> None:
    from ameriflux_mcp.ameriflux.endpoints import unwrap

    with pytest.raises(AmeriFluxApiError) as exc:
        unwrap(endpoint, payload, LABEL)  # type: ignore[arg-type]
    assert exc.value.kind == "drift" and exc.value.missing == missing
