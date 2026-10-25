---
title: "Downloads"
description: "Download AmeriFlux BASE-BADM, FLUXNET and bulk BADM with amf_download_data: a plan first, consent with confirm=true, verified files and sidecars."
type: Guide
tags:
  - tools
  - downloads
  - identity
  - data-policy
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: amf-policy
    resource: "https://ameriflux.lbl.gov/data/data-policy/"
    title: "AmeriFlux Data Policy"
    author: "team:ameriflux"
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research (section 5, downloads)"
    author: "team:idss-mesa"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (D11-D18, D37)"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-01-24T00:00:00Z"
---

# Downloads

`amf_download_data` downloads AmeriFlux data through the route the AmeriFlux website
uses: one request that tells the site PIs who is downloading and why[^amf-policy]. It
runs only over **stdio** and needs a [download identity](../getting-started/identity.md).
Inputs and result fields are in the [Tool reference](reference.md).

!!! warning "Off by default"

    Downloads are **off by default** until AmeriFlux confirms that third-party clients may use its download request (question Q1 in the project's [support questions](https://github.com/idss-mesa/ameriflux-mcp/blob/main/research/questions.md){target=_blank}). Until then the tool is not listed. To use it anyway, set
    `AMERIFLUX_MCP_DOWNLOADS__ENABLED=true` in the server's environment (or start it
    with `--downloads`); `amf_ping` reports `downloadsEnabled`.

| Product | `sites` | What arrives |
| --- | --- | --- |
| `BASE-BADM` (default) | up to 20 sites | `AMF_<SITE>_BASE-BADM_<ver>.zip`: the BASE CSV and the site's BIF |
| `FLUXNET` | up to 20 CC-BY-4.0 sites | `AMF_<SITE>_FLUXNET_<years>_v1.3_r1.zip` (FULLSET) |
| `BIF` | `AA-Flx` (sites with data) or `AA-Net` (all sites) | the bulk BADM workbook |

FLUXNET2015 and FLUXNET-CH4 files come from fluxnet.org's login-protected form, which
ameriflux-mcp does not automate (`feature_unavailable`; see
`ameriflux://guide/fluxnet2015-access`).

## 1. The plan

Without `confirm`, the tool returns a plan and sends nothing:

```json
{"tool": "amf_download_data", "arguments": {"sites": ["AR-Bal", "CA-Let"], "product": "FLUXNET"}}
```

- `disclosure`: the request AmeriFlux would receive. The user ID, email and name show as
  `configured (not shown)`; the intended-use category and the description appear in
  full, with ` [ameriflux-mcp]` appended, because that is what the PIs read. `recipients`
  says who receives it: the PIs of each site and the AmeriFlux Data Download Log.
- `eligible` and `ineligible`: here CA-Let is ineligible, because it shares its data
  under the Legacy policy and the FLUXNET product is CC-BY-4.0 only.
- `policy`: the policy code to accept (`CCBY4.0` or `LEGACY`), why, and its
  obligations. For BASE-BADM, one Legacy site makes the whole request Legacy, unless you
  ask for `policy='CCBY4.0'`, which leaves the Legacy sites out.
- `blockers` and `ready`: what must be configured first (the identity, a complete
  profile, `is_test`).
- `localCopies`: matching files already in the download directory. A new request still
  notifies the PIs, so read those first if they are current.

## 2. Consent

The agent shows the user the plan. Only if they agree does it call again with
`confirm=true` and `accept_data_policy` set to the plan's policy:

```json
{"tool": "amf_download_data", "arguments": {"sites": ["AR-Bal"], "product": "FLUXNET", "accept_data_policy": "CCBY4.0", "confirm": true}}
```

The checks run in this order, and each fails before anything is sent: the product and
policy combination, then the accepted policy (`policy_not_accepted`,
`policy_mismatch`), then the identity (`auth_required` with `identity_missing`,
`profile_missing`, `profile_incomplete` or `is_test_unset`), then at least one eligible
site.

!!! warning "Each confirmed call is a new request"

    Every `confirm=true` call sends one request, and AmeriFlux notifies the PIs again,
    so the tool is marked not idempotent[^design]. A file already on disk is kept rather than
    fetched twice, but the request is still logged.

## 3. The transfer

AmeriFlux answers with links to static files on `ftp.fluxdata.org`[^research]. The
server:

1. keeps only links on its allow-list (`/.ameriflux_downloads/`), with a plain file name,
   for a requested site; `FLUXNET-BIF` links are skipped, as amerifluxr does. Each skipped
   link is listed in `skipped` with the reason;
2. strips the `?=<user_id>` tag from each link, so the file server never receives the
   identity. The file is the same with or without it;
3. sends a HEAD for the size and ETag, and checks `downloads.max_file_bytes` (1 GiB),
   `downloads.max_bytes_per_call` (2 GiB), `downloads.max_files_per_call` and the free
   disk space;
4. streams the file to `<name>.part` with `If-Match`, then checks that the ETag, the
   Content-Length and the byte count match the HEAD, and that every zip member passes
   its CRC;
5. moves it to `<downloads.directory>/<product>/<name>` and writes `<name>.amf.json`
   beside it.

A file that fails any check is not kept (`status: failed`, `checksum_mismatch`) and no
`.part` file is left behind. With `if_exists='skip'` (the default) an existing file is
kept, and `identical` says whether it matches the server copy; `if_exists='replace'`
fetches it again unless it is identical.

## What is written

```text
~/ameriflux-downloads/
  FLUXNET/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip
  FLUXNET/AMF_AR-Bal_FLUXNET_2012-2013_v1.3_r1.zip.amf.json
  manifests/amf_download_20261024T120000Z_FLUXNET.json
```

| File | Holds |
| --- | --- |
| `<name>.amf.json` | sha256, bytes, ETag, Last-Modified, the link without its tag, site, product, policy, version, download time, `isTest`, the site's citation and the policy obligations |
| `manifests/…json` | the request (sites, product, policy, profile name, intended-use category, `isTest`), each file's outcome, skipped links, AmeriFlux's manifest rows and the citations |

Neither file holds the user ID, email, name or description. AmeriFlux also returns the
PIs' contact emails: the result reports how many (`piContactCount`), and the emails are
never stored or shown.

## After the download

`amf_preview_data(file=…)` reads the zip in place, `amf_read_bif(file=…)` reads the
site's BADM, and `amf_get_citation` gives the citations and obligations for the
reference list. See [Local files](local-files.md). To mirror the download folder to the
CyVerse Data Store, see [Sync downloads to CyVerse](../getting-started/sync-cyverse.md).

[^amf-policy]: AmeriFlux Data Policy. <https://ameriflux.lbl.gov/data/data-policy/>
[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
