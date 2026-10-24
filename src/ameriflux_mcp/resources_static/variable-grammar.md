# Variable names in AmeriFlux and FLUXNET files

`amf_describe_variables` decodes any name below; `amf_search_variables` finds names.

## BASE (FP Standard)

```
<BASE NAME>[_PI][_QC][_F][_IU][_H_V_R | _H_V_A | _#][_SD | _N]
```

- **Base name**: one of about 145 FP Standard names (`TA`, `FC`, `SW_IN`, `P_RAIN`,
  `FETCH_70`, `FC_SSITC_TEST` …); the longest match wins, so `SW_IN` is never `SW`.
- **General qualifiers**, in this order:
  - `_PI`: QA/QC-filtered or gap-filled by the tower team, independently of the network;
  - `_QC`: quality-control flag from AmeriFlux's central QA/QC;
  - `_F`: gap-filled;
  - `_IU`: instrument units (counts, mV) instead of standard units.
- **Position**, at most one:
  - `_H_V_R`: one sensor; H = horizontal position, V = vertical position (1 = highest or
    shallowest), R = replicate. Indices are relative, not distances, and may be
    renumbered in released data;
  - `_H_V_A`: replicates at one H and V averaged;
  - `_#`: a layer aggregate across horizontal positions.
- `_SD` and `_N` follow an aggregate: standard deviation and number of sensors.
- Specials: `FETCH_70/80/90` are footprint distances, not positions; `<FLUX>_SSITC_TEST`
  is the Foken flag (0 best, 2 poorest); `FETCH_FILTER` is 0 = discard, 1 = keep.
- Sensor heights and instruments: the measurement-height file
  (`amf_describe_variables(..., site=...)` or `amf_get_badm`).
- Missing values are `-9999`; time is local standard time.

Examples: `TA_F_1_1_1` (gap-filled air temperature, sensor 1,1,1); `FC_PI_F_1_1_A`
(tower-team gap-filled CO2 flux, replicates averaged); `SWC_2_3_A_SD`.

## FLUXNET (FLUXNET2015, AmeriFlux FLUXNET / ONEFlux)

| Token | Meaning |
| --- | --- |
| `_F_MDS` | gap-filled with marginal distribution sampling |
| `_ERA` | downscaled from ERA reanalysis (ERA-Interim in FLUXNET2015, ERA5 in ONEFlux v1.3) |
| `_F` | consolidated: measured, else MDS, else ERA |
| `_JSB` | LW_IN from the JSBACH algorithm |
| `_VUT` / `_CUT` | USTAR threshold variable per year / constant across years |
| `_REF`, `_USTAR50`, `_MEAN`, `_SE` | reference realization (model efficiency), 50th-percentile threshold, mean, standard error |
| `_05` … `_95` (`_XX`) | percentiles of the 40 realizations: 05, 16, 25, 50, 75, 84, 95 |
| `_NT`, `_DT`, `_SR` | nighttime, daytime, sundown-respiration partitioning (GPP, RECO) |
| `_RANDUNC`, `_JOINTUNC` | random and joint uncertainty |
| `_CORR`, `_CORR_25`, `_CORR_75` | energy-balance corrected (LE, H) |
| `_DAY`, `_NIGHT` | daytime and nighttime averages |
| `_QC` | quality flag |

Example: `GPP_NT_VUT_REF` (GPP, nighttime partitioning, variable USTAR threshold,
reference realization); `TS_F_MDS_2` is layer 2 of `TS_F_MDS_#` (1 = shallowest).

**Units change with resolution**: NEE, GPP and RECO are µmolCO2 m-2 s-1 at HH,
gC m-2 d-1 at DD, WW and MM, and gC m-2 y-1 at YY; P is mm per interval at HH, mm d-1,
then mm y-1. **QC changes meaning**: at HH `_F_MDS_QC` is 0 measured, 1 good, 2 medium,
3 poor gap-fill (consolidated `_F_QC` 2 = ERA); at DD and coarser it is the fraction of
measured and good-quality gap-filled data. In ONEFlux v1.3 files the `HH` token also
covers hourly sites: read the step from the timestamps.

**Signs**: negative NEE (and FC) is uptake; GPP and RECO are positive; NEE = RECO − GPP.

## Sources

FP Standard: `v1/fp_var` (live) or `ameriflux://reference/fp-variables`. FLUXNET:
`ameriflux://reference/fluxnet-variables`, built from the FLUXNET2015 webdoc
dictionaries and ONEFlux `var_info_definitions_*.txt`. AmeriFlux's naming page:
https://ameriflux.lbl.gov/data/aboutdata/data-variables/
