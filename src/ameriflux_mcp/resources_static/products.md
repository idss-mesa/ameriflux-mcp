# AmeriFlux and FLUXNET data products

| Product | Collection | Policies | What it is | Here |
| --- | --- | --- | --- | --- |
| `BASE-BADM` | AmeriFlux | CCBY4.0, LEGACY | Half-hourly or hourly flux and meteorological data as submitted and QA/QC'd by AmeriFlux (FP Standard names), with the site's BADM | discover, availability, cite, download, read |
| `BIF` | AmeriFlux | CCBY4.0, LEGACY | BADM site metadata in the BADM Interchange Format (xlsx) | membership, cite (BASE DOI), bulk download, read |
| `FLUXNET` (FLUXNET-1F) | AmeriFlux | CCBY4.0 only | ONEFlux v1.3 processing of CC-BY BASE data: gap-filled, USTAR-filtered, partitioned (GPP, RECO), HH/DD/WW/MM/YY, ERA5 downscaled meteorology | discover, availability, cite, download, read |
| `FLUXNET2015` | FLUXNET | CCBY4.0 (Tier One), TIER2 | The frozen 2015 synthesis (212 sites, data to 2014), FULLSET and SUBSET | discover, availability, cite, read local files |
| `FLUXNET-CH4` | FLUXNET | CCBY4.0, TIER2 | The methane community product V1.0 (81 sites) | discover, availability (citations and reading in v0.2) |

Invalid product × policy pairs fail before any request (`invalid_combination`): the
AmeriFlux API answers them with 200 and empty rows. FLUXNET with LEGACY is
`fluxnet_requires_ccby`: ONEFlux processes CC-BY data only, so Legacy sites have no
FLUXNET product.

## Which one to use

- Gap-filled annual or daily budgets, GPP or ecosystem respiration: **FLUXNET**
  (FLUXNET-1F), `resolution='DD'` or coarser. HH in v1.3 file names is the finest step,
  half-hourly or hourly.
- The original measurements, more variables, recent data, Legacy sites: **BASE-BADM**.
- Studies that must match the 2015 synthesis or include non-American sites:
  **FLUXNET2015**. It is frozen; fluxnet.org calls it outdated in favour of the FLUXNET
  Shuttle.
- Site metadata only (ecosystem, instruments, UTC offsets, team, funding): **BIF**, or
  `amf_get_badm` for what the API exposes without a download.

## FULLSET and SUBSET

FULLSET has every ONEFlux variable (about 232 names); SUBSET is a curated selection (about
72) for non-specialists. AmeriFlux FLUXNET downloads are always FULLSET; `view='subset'` in
`amf_preview_data` shows the SUBSET columns of a FULLSET file.
`amf_search_variables(dictionary='fluxnet_subset')` lists them.

## Bulk BADM

`amf_download_data(product='BIF', sites=['AA-Flx'])` (every site with flux data) or
`['AA-Net']` (every registered site) sends a BASE-BADM request for that bulk ID, as
amerifluxr does; the per-site BIF also comes inside every BASE-BADM zip. BADM has no DOI
of its own: cite the site's BASE-BADM DOI.

## Versions

BASE versions are `<data>-<processing>` (`28-5`); FLUXNET versions are `v1.3_r1`.
Citations carry the version ("Ver. 28-5"); cite the version you downloaded (its BIF or
sidecar records it).
