---
title: "Variables"
description: "Find and decode AmeriFlux BASE and FLUXNET variable names with amf_search_variables and amf_describe_variables: qualifiers, units per resolution, QC, heights."
type: Guide
tags:
  - tools
  - variables
  - fluxnet
  - qa-qc
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research (section 7)"
    author: "team:idss-mesa"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (D35)"
    author: "team:idss-mesa"
  - id: amf-variables
    resource: "https://ameriflux.lbl.gov/data/aboutdata/data-variables/"
    title: "AmeriFlux data variables"
    author: "team:ameriflux"
  - id: fullset
    resource: "https://fluxnet.org/data/fluxnet2015-dataset/fullset-data-product/"
    title: "FLUXNET2015 FULLSET data product"
    author: "team:fluxnet"
status: stable
stale_after: "2027-04-24T00:00:00Z"
---

# Variables

Flux files name every column with a code such as `TA_F_1_1_1` or `GPP_NT_VUT_REF`. Two
tools turn those codes into something you can use. Neither needs an account, and both
work over stdio and HTTP. Inputs and result fields are in the
[Tool reference](reference.md).

## Two kinds of name

**BASE names** (AmeriFlux BASE, the FP Standard[^amf-variables]) are a base name and
qualifiers:

```
<BASE NAME>[_PI][_QC][_F][_IU][_H_V_R | _H_V_A | _#][_SD | _N]
```

| Part | Meaning |
| --- | --- |
| Base name | One of about 145 FP Standard names (`TA`, `FC`, `SW_IN`, `FETCH_70`, `FC_SSITC_TEST`) |
| `_PI` | Filtered or gap-filled by the tower team, independently of the network |
| `_QC` | Quality flag from AmeriFlux's central QA/QC |
| `_F` | Gap-filled |
| `_IU` | Instrument units (counts, mV) rather than standard units |
| `_H_V_R` | One sensor: horizontal position, vertical position (1 = highest or shallowest), replicate |
| `_H_V_A` | Replicates at one position, averaged |
| `_#` | Layer aggregate across horizontal positions |
| `_SD`, `_N` | Standard deviation and number of sensors in an aggregate |

**FLUXNET names** (FLUXNET2015 FULLSET and SUBSET[^fullset], and the AmeriFlux FLUXNET
product made with ONEFlux v1.3) add processing tokens: `_F_MDS` (gap-filled with MDS),
`_ERA` (downscaled from reanalysis), `_VUT`/`_CUT` (USTAR threshold varies by year or is
constant), `_REF` and the percentiles `_05` … `_95`, `_NT`/`_DT`/`_SR` (partitioning
method), `_RANDUNC`, `_CORR`, `_DAY`/`_NIGHT`, `_QC`.

## Units and QC change with resolution

FLUXNET files come at HH (half-hourly or hourly), DD, WW, MM and YY, and one name means
different units at each[^research]:

| Variable | HH | DD, WW, MM | YY |
| --- | --- | --- | --- |
| `NEE_VUT_REF`, `GPP_NT_VUT_REF`, `RECO_NT_VUT_REF` | µmolCO2 m-2 s-1 | gC m-2 d-1 | gC m-2 y-1 |
| `P_F` | mm (per interval) | mm d-1 | mm y-1 |
| `TA_F_MDS_QC` | 0 measured, 1 good, 2 medium, 3 poor gap-fill | fraction of measured and good data | fraction |

Every FLUXNET result carries `unitsByResolution`; pass `resolution` to get one unit and
the QC meaning at that resolution. Negative NEE and FC are uptake; GPP and RECO are
positive.

## amf_search_variables

Words match names, descriptions and units (prefixes count). Choose a `dictionary`:

| `dictionary` | Contents |
| --- | --- |
| `fp` | The FP Standard list for BASE, read live from the AmeriFlux API with its QA/QC ranges (`plausibleRange`) |
| `fluxnet` | Names the AmeriFlux FLUXNET product defines (ONEFlux v1.3) |
| `fluxnet_fullset`, `fluxnet_subset` | FLUXNET2015 FULLSET (232 names) and SUBSET (72) |
| `all` | All of the above (default) |

`category` filters by FP type (`GASES`, `MET_SOIL`) or FLUXNET section (`PARTITIONING`,
`SUNDOWN`); `resolution` keeps the FLUXNET names produced at it.

```json
{"tool": "amf_search_variables", "arguments": {"query": "soil temperature"}}
{"tool": "amf_search_variables", "arguments": {"query": "GPP", "dictionary": "fluxnet_subset", "resolution": "DD"}}
```

Dictionary names with `XX` or `#` stand for many columns: `NEE_VUT_XX` is `NEE_VUT_05`
to `NEE_VUT_95`, and `TS_F_MDS_#` is `TS_F_MDS_1` (shallowest), `TS_F_MDS_2`, …

## amf_describe_variables

Up to 20 names per call. Each result gives the base name and its FP definition, every
qualifier or token with its meaning, the position, the units, the FLUXNET definition
(with the dictionary key: `NEE_VUT_05` is `NEE_VUT_XX`), a sign convention where one
applies, and `didYouMean` for names it does not recognize. A name valid in both grammars
(`TA_F`) gets both readings, with a note.

With `site`, each name also gets:

- whether the site's BASE data include the base name (from the catalog);
- sensor heights and instruments from AmeriFlux's measurement-height file;
- yearly coverage per column from amerifluxr's snapshot, marked with its date
  (2025-10-20 as of this writing; it lags the current BASE release).

```json
{"tool": "amf_describe_variables", "arguments": {"names": ["GPP_NT_VUT_REF", "TA_F_MDS_QC"], "resolution": "DD"}}
{"tool": "amf_describe_variables", "arguments": {"names": ["TA", "SWC_1_1_1"], "site": "US-Ha1"}}
```

The first call with `site` downloads the measurement-height file (about 2.3 MB) and the
coverage snapshot (about 6.5 MB). Both are cached: heights for 24 hours, coverage for
7 days.

## Sources and resources

| URI | Content |
| --- | --- |
| `ameriflux://guide/variable-grammar` | The grammar on this page, for agents |
| `ameriflux://reference/fp-variables` | The FP Standard list (live, or the bundled snapshot when the API is unreachable) |
| `ameriflux://reference/fluxnet-variables` | The FLUXNET dictionary with units and notes per resolution |

The FLUXNET dictionary is built by `scripts/build_variable_dictionaries.py` from the
FLUXNET2015 webdoc dictionaries and ONEFlux's `var_info_definitions` files. The micro
sign is restored where ONEFlux stores it as a replacement character[^design].

[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
[^amf-variables]: AmeriFlux data variables. <https://ameriflux.lbl.gov/data/aboutdata/data-variables/>
[^fullset]: FLUXNET2015 FULLSET data product. <https://fluxnet.org/data/fluxnet2015-dataset/fullset-data-product/>
