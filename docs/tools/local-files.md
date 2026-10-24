---
title: "Local files"
description: "Find, preview and read AmeriFlux and FLUXNET files on your computer with amf_list_files, amf_preview_data and amf_read_bif, inside their zips and offline."
type: Guide
tags:
  - tools
  - local-files
  - fluxnet
  - badm
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research (section 6)"
    author: "team:idss-mesa"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (D23, D36)"
    author: "team:idss-mesa"
  - id: oneflux-readme
    resource: "https://github.com/fluxnet/ONEFlux/blob/main/oneflux/metadata/fluxnet_data_docs/README.txt"
    title: "ONEFlux FLUXNET data product README"
    author: "team:fluxnet"
status: stable
stale_after: "2027-04-24T00:00:00Z"
---

# Local files

Three tools read the AmeriFlux and FLUXNET files already on your computer. They run only
over **stdio** (a hosted server has no access to your disk), never use the network, and
read archives **in place**: nothing is extracted. Inputs and result fields are in the
[Tool reference](reference.md).

## Where they look

Files are readable only inside the **download directory** (`downloads.directory`,
default `~/ameriflux-downloads`) and any folder in **`local.roots`**
([Configuration](../getting-started/configuration.md)):

```bash
export AMERIFLUX_MCP_LOCAL__ROOTS=~/fluxnet2015,~/flux-archive
```

Paths are relative to a root (or absolute inside one). `archive.zip::member.csv` names
a member. A path that leaves the roots, including through a symbolic link, fails with
`invalid_argument` (`outside_local_roots`). FLUXNET2015 zips need a fluxnet.org account,
so you download them yourself and add their folder to `local.roots`; the server never
automates that login.

## amf_list_files

Lists every file whose name AmeriFlux or FLUXNET gave it, and classifies each archive
member[^research]:

| Family | Files |
| --- | --- |
| `base` | `AMF_<SITE>_BASE-BADM_<X-Y>.zip` holding `AMF_<SITE>_BASE_(HH\|HR)_<X-Y>.csv` and the site's BIF workbook |
| `bif` | `AMF_<SITE>_BIF_<date>.xlsx`, and the bulk `AA-Flx`/`AA-Net` files |
| `fluxnet` | AmeriFlux FLUXNET (ONEFlux v1.3) zips: FLUXMET, ERA5 and BIFVARINFO files per resolution, a BIF CSV, README and licence[^oneflux-readme] |
| `fluxnet2015` | FULLSET and SUBSET zips: data per resolution, ERAI, AUXMETEO and AUXNEE |
| `fluxnet_ch4` | Listed; reading arrives in v0.2 |

Each entry gives the site, resolution, years and version; members that cannot be read
say why (see [Safety](#safety)). Filter by `family` or `site`, or give a folder or a
single archive as `path`.

## amf_preview_data

Reads one CSV, by `file` or by `site` and `product` (the newest local version), and by
default the half-hourly or hourly member of an archive (`resolution` picks another).

- **Summary** (default): per column the count, missing values (`-9999`), min, max, mean,
  units at the file's resolution, and `outOfRange`: values beyond the FP Standard range
  ±5%, counted but kept. The file info gives the time step read from the timestamps,
  the time range, the `#` header lines of BASE files, and the site's UTC offsets.
- **Rows** (`mode='rows'`): a page of rows (`max_rows`, `offset`) within `start`/`end`.
  `to_utc=true` adds UTC timestamps, applying the offset in force on each row's date.
- **QC**: `qc_max` keeps HH/HR values whose `_QC` flag is at most the threshold (0
  measured … 3 poor); `qc_min_fraction` keeps DD and coarser values whose QC fraction
  is at least the threshold. Rejected values become null and are counted in
  `qcFiltered`.
- **SUBSET view**: `view='subset'` keeps only the FLUXNET2015 SUBSET variables of an
  AmeriFlux FLUXNET file.
- **Aux tables**: AUXMETEO and AUXNEE are read as plain tables, with text values
  listed.

```json
{"tool": "amf_preview_data", "arguments": {"site": "US-Ha1", "product": "FLUXNET", "resolution": "DD", "columns": ["NEE_VUT_REF", "GPP_NT_VUT_REF"], "qc_min_fraction": 0.8}}
{"tool": "amf_preview_data", "arguments": {"file": "AMF_US-Ha1_BASE-BADM_28-5.zip", "mode": "rows", "start": "2020-07-01", "end": "2020-07-02", "to_utc": true}}
```

!!! note "HH can mean hourly"

    ONEFlux v1.3 names its finest resolution `HH` even for hourly sites; the preview
    reads the step from `TIMESTAMP_START`/`TIMESTAMP_END` and says so when they differ.

A scan stops after `end`, or once it has read 256 MiB or run for 20 s
(`truncatedReason: budget`). Half-hourly BASE files reach hundreds of megabytes, so for
long records start with the DD or MM file, or narrow `start`, `end` and `columns`.

## amf_read_bif

Reads BADM Interchange Format files: the BIF workbook of a BASE-BADM zip, the BIF CSV of
a FLUXNET zip, or a BIF file on its own. It returns entries by group (filter with
`groups`, and with `site_id` in bulk files), the UTC offsets with their start dates, the
DOI and citation recorded for that version, and the funding acknowledgments.

**Personal data is withheld by default**: emails, postal and shipping addresses, and the
names of private land owners. They are shown only when you pass `include_contacts` and
the operator enabled `privacy.allow_contact_emails`. The citation in a BIF is the one of
that file's version; `amf_get_citation` gives the current one.

## Safety

Archives are read in place through a checker that refuses members with absolute or
`..` paths, symbolic links, encrypted members, members over 1 GiB uncompressed, and
members over 1 MiB that compress more than 200:1 (zip bombs)[^design]. Reads also stop if
a member decompresses past its declared size.

## Resources

| URI | Content |
| --- | --- |
| `ameriflux://guide/file-formats` | File names, CSV conventions, BIF and previews, for agents |
| `ameriflux://guide/fluxnet2015-access` | Getting FLUXNET2015 zips yourself and reading them here |

[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
[^oneflux-readme]: ONEFlux FLUXNET data product README. <https://github.com/fluxnet/ONEFlux/blob/main/oneflux/metadata/fluxnet_data_docs/README.txt>
