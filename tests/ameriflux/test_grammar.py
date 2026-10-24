"""The variable-name grammar: a golden table, templates and a Hypothesis round trip."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ameriflux_mcp.ameriflux.variables.grammar import (
    GENERAL,
    Position,
    compose,
    fluxnet_template,
    parse,
    snapshot_fp_names,
)

FP = snapshot_fp_names()


@pytest.mark.parametrize(
    ("name", "grammar", "basename", "general", "position"),
    [
        ("TA", "base", "TA", (), None),
        ("TA_F_1_1_1", "base", "TA", ("F",), ("sensor", 1, 1, 1, None, None)),
        ("FC_PI_F_1_1_A", "base", "FC", ("PI", "F"), ("replicate_average", 1, 1, None, None, None)),
        ("SWC_2_3_A_SD", "base", "SWC", (), ("replicate_average", 2, 3, None, None, "SD")),
        ("TS_3", "base", "TS", (), ("layer_average", None, None, None, 3, None)),
        ("TS_3_N", "base", "TS", (), ("layer_average", None, None, None, 3, "N")),
        ("LE_PI_QC_F_IU", "base", "LE", ("PI", "QC", "F", "IU"), None),
        ("P_RAIN_1_1_1", "base", "P_RAIN", (), ("sensor", 1, 1, 1, None, None)),
        ("SW_IN_1_1_2", "base", "SW_IN", (), ("sensor", 1, 1, 2, None, None)),
        ("FETCH_70", "base", "FETCH_70", (), None),
        ("FETCH_90_1_1_1", "base", "FETCH_90", (), ("sensor", 1, 1, 1, None, None)),
        ("FC_SSITC_TEST", "base", "FC_SSITC_TEST", (), None),
        ("t_sonic_sigma", "base", "T_SONIC_SIGMA", (), None),
        ("GPP_NT_VUT_REF", "fluxnet", "GPP", (), None),
        ("NEE_CUT_XX", "fluxnet", "NEE", (), None),
        ("NEE_VUT_REF_RANDUNC_N", "fluxnet", "NEE", (), None),
        ("TA_F_MDS_QC", "fluxnet", "TA", (), None),
        ("TS_F_MDS_2_QC", "fluxnet", "TS", (), None),
        ("LE_CORR_75", "fluxnet", "LE", (), None),
        ("RECO_SR", "fluxnet", "RECO", (), None),
        ("SW_IN_POT", "fluxnet", "SW_IN", (), None),
        ("BOGUS_X", "unknown", "BOGUS", (), None),
        ("TA_QC_PI", "unknown", "TA", (), None),  # out of order
    ],
)
def test_golden(
    name: str,
    grammar: str,
    basename: str,
    general: tuple[str, ...],
    position: tuple[object, ...] | None,
) -> None:
    parsed = parse(name)
    assert parsed.grammar == grammar
    assert parsed.basename == basename
    assert parsed.general == general
    if position is None:
        assert parsed.position is None
    else:
        p = parsed.position
        assert p is not None
        assert (p.kind, p.h, p.v, p.r, p.layer, p.statistic) == position


def test_tokens_explain_fluxnet_names() -> None:
    gpp = parse("GPP_NT_VUT_REF")
    assert [t.kind for t in gpp.tokens] == ["partitioning", "ustar", "realization"]
    assert not gpp.unknown and gpp.known_basename
    nee = parse("NEE_VUT_05_QC")
    assert [t.text for t in nee.tokens] == ["_VUT", "_05", "_QC"]
    assert nee.is_qc and not nee.is_gapfilled
    ts = parse("TS_F_MDS_2")
    assert [t.kind for t in ts.tokens] == ["gapfill", "layer"] and ts.is_gapfilled
    era = parse("TA_ERA")
    assert era.tokens[0].kind == "gapfill" and "ERA5" in era.tokens[0].meaning


def test_base_qualifier_meanings_and_notes() -> None:
    parsed = parse("FC_PI_F_1_1_A")
    assert [t.kind for t in parsed.tokens] == ["pi", "gapfill", "replicate_average"]
    assert "tower team" in parsed.tokens[0].meaning
    assert any("footprint" in n for n in parse("FETCH_80").notes)
    assert any("Foken" in n for n in parse("LE_SSITC_TEST").notes)
    assert any("not an FP Standard" in n for n in parse("XYZ_1").notes)


@pytest.mark.parametrize(
    ("name", "template"),
    [
        ("NEE_VUT_05", "NEE_VUT_XX"),
        ("nee_cut_95_qc", "NEE_CUT_XX_QC"),
        ("GPP_DT_VUT_50", "GPP_DT_VUT_XX"),
        ("TS_F_MDS_2", "TS_F_MDS_#"),
        ("SWC_F_MDS_10_QC", "SWC_F_MDS_#_QC"),
        ("LE_CORR_25", "LE_CORR_25"),
        ("NEE_VUT_REF", "NEE_VUT_REF"),
    ],
)
def test_fluxnet_template(name: str, template: str) -> None:
    assert fluxnet_template(name) == template


def test_custom_fp_list() -> None:
    assert parse("NEWVAR_F_1_1_1", {"NEWVAR"}).grammar == "base"
    assert parse("NEWVAR_F_1_1_1").grammar == "unknown"


def test_compose_rejects_repeats() -> None:
    with pytest.raises(ValueError):
        compose("TA", ["F", "F"])
    assert compose("TA", ["F", "PI"]) == "TA_PI_F"


# ---------------------------------------------------------------------- properties

BASENAMES = sorted(n for n in FP if not n.startswith("TIMESTAMP"))
index = st.integers(min_value=1, max_value=12)
positions = st.one_of(
    st.none(),
    st.builds(lambda h, v, r: Position("sensor", h=h, v=v, r=r), index, index, index),
    st.builds(
        lambda h, v, s: Position("replicate_average", h=h, v=v, statistic=s),
        index,
        index,
        st.sampled_from([None, "SD", "N"]),
    ),
    st.builds(
        lambda layer, s: Position("layer_average", layer=layer, statistic=s),
        index,
        st.sampled_from([None, "SD", "N"]),
    ),
)
generals = st.lists(st.sampled_from(GENERAL), unique=True).map(
    lambda gs: tuple(g for g in GENERAL if g in gs)
)


@settings(max_examples=400, deadline=None)
@given(st.sampled_from(BASENAMES), generals, positions)
def test_round_trip(basename: str, general: tuple[str, ...], position: Position | None) -> None:
    name = compose(basename, general, position)
    parsed = parse(name)
    assert parsed.grammar == "base", name
    assert (parsed.basename, parsed.general, parsed.position) == (basename, general, position)
    assert compose(parsed.basename, parsed.general, parsed.position) == name


@settings(max_examples=300, deadline=None)
@given(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_#", min_size=1, max_size=40))
def test_parse_never_raises(text: str) -> None:
    parsed = parse(text)
    assert parsed.grammar in ("base", "fluxnet", "unknown")
    assert parsed.name == text.strip().upper()
