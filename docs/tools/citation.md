---
title: "Citations and BADM"
description: "Cite AmeriFlux and FLUXNET2015 sites with amf_get_citation (versioned text, policy obligations, acknowledgments) and read site metadata with amf_get_badm."
type: Guide
tags:
  - tools
  - citation
  - data-policy
  - badm
generated:
  by: "claude/opus-5.5"
  at: "2026-10-24T00:00:00Z"
sources:
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research (sections 4 and 8)"
    author: "team:idss-mesa"
  - id: design
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md"
    title: "ameriflux-mcp design (D9, D10, D35)"
    author: "team:idss-mesa"
  - id: amf-policy
    resource: "https://ameriflux.lbl.gov/data/data-policy/"
    title: "AmeriFlux Data Policy"
    author: "team:ameriflux"
  - id: fluxnet-policy
    resource: "https://fluxnet.org/data/data-policy/"
    title: "FLUXNET Data Policy"
    author: "team:fluxnet"
status: stable
stale_after: "2027-04-24T00:00:00Z"
---

# Citations and BADM

`amf_get_citation` gathers everything you need to credit a set of sites, and
`amf_get_badm` returns the site metadata the API exposes. Both work over stdio and HTTP
without an account. [Citing AmeriFlux and FLUXNET data](../about/citing-ameriflux.md)
explains the policies behind them.

## amf_get_citation

Give up to 50 sites and one product:

| `product` | Citation |
| --- | --- |
| `BASE-BADM` (default) | AmeriFlux's own text for the site's BASE DOI, with the version (`Ver. 28-5`) |
| `BIF` (BADM) | The BASE-BADM citation: BADM has no DOI of its own |
| `FLUXNET` (FLUXNET-1F) | AmeriFlux's text for the FLUXNET DOI (`Ver. v1.3_r1 (1991-2025)`) |
| `FLUXNET2015` | Built from the DOI record the way the FLUXNET DOI page shows it: authors, Tier Two years, title, "Dataset", DOI |

FLUXNET-CH4 citations come in v0.2 (`feature_unavailable` until then).

The result has:

- **`citations`**: one per site, cited as written in the reference list (not in
  supplementary material). `source` says where the text came from: `amfcdn` (AmeriFlux),
  `constructed` (FLUXNET2015) or `datacite` (a fallback when the AmeriFlux DOI service is
  down; it has no version and comes with a `versionMissing` warning). Set
  `include_bibtex` for a BibTeX entry per site.
- **`missing`**: requested sites without a citation and why (a Legacy site has no FLUXNET
  product; US-xSR is not part of FLUXNET2015).
- **`effectivePolicy`**: the policy the whole selection must follow, with each obligation
  marked `required` or `recommended`[^design]. Mixing CC-BY and Legacy sites means Legacy;
  any Tier Two site makes FLUXNET2015 Tier Two.
- **`acknowledgments`**: verbatim text from the policy page[^amf-policy]. Legacy data name
  the data *portal*, CC-BY data the data *service*, and FLUXNET adds the networks and ERA5
  text.
- **`siteFunding`**: under Legacy, each site's sponsors from its DOI record, to
  acknowledge. When a record has none, a note points to the site's BADM.
- **`dataAvailability`**: the sentence for a Data Availability section, with the product
  filled in and the AmeriFlux-listed `[SOURCE]` options.
- **`processingReferences`**: Chu et al. 2023 (BASE) or Pastorello et al. 2020 (FLUXNET,
  FLUXNET2015).

```json
{"tool": "amf_get_citation", "arguments": {"sites": ["US-Ha1", "CA-Let"]}}
{"tool": "amf_get_citation", "arguments": {"sites": ["US-Ha1", "RU-Sam"], "product": "FLUXNET2015"}}
```

The first call returns the Legacy policy, because CA-Let shares its data under it; the
second returns Tier Two, because RU-Sam is Tier Two only[^research].

## amf_get_badm

BADM (Biological, Ancillary, Disturbance and Metadata) for one site, grouped as the API
exposes it:

| Section | Content |
| --- | --- |
| `site` | Location (GRP_LOCATION), IGBP and climate with AmeriFlux's descriptions, tower dates, site URL, description |
| `team` | Names, roles and institutions; emails only under the two-flag rule ([Configuration](../getting-started/configuration.md)) |
| `disturbance` | Dominant disturbance and management, and the flux gas species measured |
| `funding` | Sponsor and contributor organizations from the DOI record: what a Legacy site asks you to acknowledge |
| `references` | The site's reference papers, paged (`references_limit`, `references_offset`) |
| `instruments` | Variables with height (m; negative is depth), instrument models and dates, from the measurement-height file; `variables` narrows them by base name (`TA`) or exact column (`SWC_1_1_1`) |

The complete BADM, with every group and its dates, is the BIF file inside each BASE-BADM
download.

```json
{"tool": "amf_get_badm", "arguments": {"site": "US-Ha1", "include": ["funding", "instruments"], "variables": ["TA"]}}
```

## Resources

| URI | Content |
| --- | --- |
| `ameriflux://guide/data-policy` | CC-BY-4.0 and Legacy, Tier One and Tier Two, and why mixing escalates |
| `ameriflux://reference/acknowledgments` | The verbatim texts, with the date they were checked against the policy pages[^fluxnet-policy] |

[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
[^design]: ameriflux-mcp design. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/DESIGN.md>
[^amf-policy]: AmeriFlux Data Policy. <https://ameriflux.lbl.gov/data/data-policy/>
[^fluxnet-policy]: FLUXNET Data Policy. <https://fluxnet.org/data/data-policy/>
