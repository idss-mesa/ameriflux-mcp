# AmeriFlux and FLUXNET data policies

Every site's data are shared under one policy. The policy decides what you must do when
you publish, and **mixing escalates**: one stricter site makes the stricter policy apply
to the whole selection. `amf_get_availability` labels each site-year with its policy and
`amf_get_citation` returns the policy a selection must follow, its obligations and the
verbatim acknowledgments.

## AmeriFlux (BASE-BADM, BADM, FLUXNET)

| Policy | Code | What it asks |
| --- | --- | --- |
| CC-BY-4.0 license (revised December 2025) | `CCBY4.0` | Cite each site's DOI in the reference list (not supplementary material); acknowledge "Funding for the AmeriFlux data service was provided by the U.S. Department of Energy Office of Science."; add the Data Availability sentence if the paper has that section; informing the data providers is recommended. |
| Legacy Data Policy | `LEGACY` | Contact the data contributors when you start in-depth analysis (they may become co-authors); cite the DOI; acknowledge the site's funding; acknowledge the AmeriFlux data **portal** (not service); inform the data providers before publication; use the AmeriFlux logo or link in presentations. |

- **CC-BY + Legacy = Legacy** for everything in the selection.
- The **FLUXNET** product (FLUXNET-1F, ONEFlux) exists only for CC-BY sites: Legacy
  sites have none, and FLUXNET under LEGACY is `invalid_argument`.
- FLUXNET data add a second acknowledgment (FLUXNET networks and ERA5).
- Processing references: Chu et al. 2023 (BASE), Pastorello et al. 2020 (FLUXNET).
- BADM (the BIF file) has no DOI of its own: cite the site's BASE-BADM DOI.

## FLUXNET2015 and FLUXNET-CH4

| Policy | Code | What it asks |
| --- | --- | --- |
| CC-BY-4.0 (formerly Tier One) | `CCBY4.0` | Cite Pastorello et al. 2020 (FLUXNET2015); list each site by FLUXNET ID and/or DOI; informing providers is recommended. |
| Tier Two | `TIER2` | Scientific and educational use only; contact the providers when you begin research that could lead to a publication; give them at least three weeks after the first draft; list each site in a table. Six sites are Tier Two only (RU-Sam, RU-SkP, RU-Tks, RU-Vrk, SE-St1, ZA-Kru) and are not part of Pastorello et al. 2020. |

- **Any Tier Two site makes the whole synthesis Tier Two.**
- FLUXNET2015 is frozen and labelled "outdated" by fluxnet.org; its downloads need a
  fluxnet.org account (never automated by this server).

## Disclosure

When you download AmeriFlux data, your intended use and description are sent to the site
PIs and posted to the AmeriFlux Data Download Log. See `ameriflux://guide/identity`.

## Sources

- AmeriFlux data policy: https://ameriflux.lbl.gov/data/data-policy/
- FLUXNET data policy: https://fluxnet.org/data/data-policy/
- Verbatim texts: `ameriflux://reference/acknowledgments` (checked 2026-10-24).
