# AmeriFlux and FLUXNET files

`amf_list_files` finds these files in the download directory and `local.roots`;
`amf_preview_data` reads the CSVs (inside their zips, never extracted); `amf_read_bif`
reads the BIF metadata. All three are stdio only and never use the network.

## Names

| Family | Archive | Members or files |
| --- | --- | --- |
| BASE | `AMF_<SITE>_BASE-BADM_<X-Y>.zip` | `AMF_<SITE>_BASE_(HH|HR)_<X-Y>.csv`, `AMF_<SITE>_BIF_<YYYYMMDD>.xlsx` |
| BADM bulk | — | `AMF_(AA-Flx|AA-Net)_BIF_(CCBY4|LEGACY)_<YYYYMMDD>.xlsx` (many sites) |
| AmeriFlux FLUXNET (ONEFlux v1.3+) | `<NET>_<SITE>_FLUXNET_<YS>-<YE>_v1.3_r1.zip` | `…_FLUXNET_FLUXMET_<T>_…csv` (flux and met), `…_ERA5_<T>_…csv`, `…_BIFVARINFO_<T>_…csv`, `…_FLUXNET_BIF_…csv`, `README.txt`, `DATA_POLICY_LICENSE_AND_INSTRUCTIONS.txt` |
| FLUXNET2015 | `FLX_<SITE>_FLUXNET2015_(FULLSET|SUBSET)_<YS>-<YE>_<n-n>.zip` | `…_(FULLSET|SUBSET)_(HH|HR|DD|WW|MM|YY)_…csv`, `…_ERAI_<T>_1989-2014_…csv`, `…_AUXMETEO_…csv`, `…_AUXNEE_…csv` |
| FLUXNET-CH4 | — | `FLX_<SITE>_FLUXNET-CH4_(HH|HR|DD)_…csv` (listed; read in v0.2) |

`<T>` is the resolution. In ONEFlux v1.3 names `HH` means the finest step, half-hourly
**or hourly**: the step is read from the timestamps. BASE and FLUXNET2015 write `HR` for
hourly sites.

## Inside the CSVs

- Comma-separated, first row the header. BASE files start with `# Site:` and `# Version:`
  lines; FLUXNET files do not.
- Missing values are `-9999` (also `-9999.0`, `-9999.9`).
- Time is **local standard time** (no daylight saving). The offset to UTC is the BIF's
  `GRP_UTC_OFFSET`, which can change over a site's record (`UTC_OFFSET_DATE_START`);
  `to_utc=true` applies the offset in force for each row.
- HH, HR and WW files use `TIMESTAMP_START`/`TIMESTAMP_END`; DD, MM and YY use one
  `TIMESTAMP` (`YYYYMMDD`, `YYYYMM`, `YYYY`). The last record of a year ends at the next
  year's `…01010000`; rows belong to the year they start in.
- Column order is not guaranteed: always select columns by name.
- AUXMETEO and AUXNEE are plain tables (downscaling and USTAR results), not time series.

## Previews

A summary gives, per column: count, missing, min, max, mean, units at the file's
resolution, and `outOfRange` (beyond the FP Standard range ±5%, counted and kept).
`qc_max` (HH/HR: keep flags 0..n) and `qc_min_fraction` (DD and coarser) null values
whose `_QC` companion fails. `view='subset'` keeps the FLUXNET2015 SUBSET variables of
an AmeriFlux FLUXNET file. A scan stops after `end`, after 256 MiB, or after 20 s; for
long records read the DD or MM file first.

## BIF

Five columns: `SITE_ID, GROUP_ID, VARIABLE_GROUP, VARIABLE, DATAVALUE`; rows sharing a
GROUP_ID are one entry. Emails, postal and shipping addresses and private land owners
are withheld unless the user asks and the operator allows contacts. The DOI citation in a
BIF is the one of that file's version; `amf_get_citation` gives the current one.

## Safety

Archives are read in place. Members with absolute or `..` paths, symbolic links,
encrypted members, members over 1 GiB and members compressing more than 200:1 are
refused, and `amf_list_files` says why. Only files inside the download directory or a
configured root can be read.
