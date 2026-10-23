---
title: "Citing AmeriFlux and FLUXNET data"
description: "How to cite AmeriFlux BASE, AmeriFlux FLUXNET and FLUXNET2015 data: per-site DOIs, required acknowledgments, policy obligations, and citing ameriflux-mcp."
type: Policy
tags:
  - about
  - citation
  - data-policy
  - doi
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: amf-policy
    resource: "https://ameriflux.lbl.gov/data/data-policy/"
    title: "AmeriFlux Data Policy"
    author: "team:ameriflux"
  - id: fluxnet-policy
    resource: "https://fluxnet.org/data/data-policy/"
    title: "FLUXNET Data Policy"
    author: "team:fluxnet"
  - id: chu-2023
    resource: "https://doi.org/10.1038/s41597-023-02531-2"
    title: "Chu et al. (2023), AmeriFlux BASE data pipeline to support network growth and data sharing, Sci Data 10, 614"
    author: "Chu, H. et al."
  - id: pastorello-2020
    resource: "https://doi.org/10.1038/s41597-020-0534-3"
    title: "Pastorello et al. (2020), The FLUXNET2015 dataset and the ONEFlux processing pipeline for eddy covariance data, Sci Data 7, 225"
    author: "Pastorello, G. et al."
status: stable
stale_after: "2027-04-23T00:00:00Z"
---

# Citing AmeriFlux and FLUXNET data

AmeriFlux and FLUXNET data come from individual tower teams, and the data policies ask
you to credit each site you use. `amf_get_citation` assembles everything on this page
for a list of sites; this page explains what it returns and why. The text below follows
the AmeriFlux data policy (CC-BY-4.0 license revised December 2025) and the FLUXNET data
policy as read on 2026-10-22[^amf-policy][^fluxnet-policy]; the policy pages are
authoritative.

## One citation per site

Every AmeriFlux product of every site has its own DOI under `10.17190/AMF/`, and every
FLUXNET2015 site one under `10.18140/FLX/`. Cite each site in the reference list, not in
supplementary material. AmeriFlux's recommended form includes the product version:

> J. William Munger, Shawn Urbanski, Michael Golden, Carol Barford, Jaclyn Matthes,
> Steven Wofsy (2026), AmeriFlux BASE US-Ha1 Harvard Forest EMS Tower (HFR1), Ver. 28-5,
> AmeriFlux AMP, (Dataset). https://doi.org/10.17190/AMF/1246059

> … (2026), AmeriFlux FLUXNET-1F US-Ha1 Harvard Forest EMS Tower (HFR1), Ver. v1.3_r1
> (1991-2025), AmeriFlux AMP, (Dataset). https://doi.org/10.17190/AMF/1871137

The version, year and publisher in this form differ from what generic DOI services
(DataCite, doi.org) return, so prefer AmeriFlux's form. BADM metadata downloaded with a
product is cited with that product's DOI. AmeriFlux does not publish ready-made citation
text for FLUXNET2015 sites; `amf_get_citation` builds it from the site's DOI, title and
contributors.

## Acknowledgments

For **CC-BY-4.0** AmeriFlux data:

> Funding for the AmeriFlux data service was provided by the U.S. Department of Energy
> Office of Science.

For **Legacy** data the wording names the data *portal*:

> Funding for the AmeriFlux data portal was provided by the U.S. Department of Energy
> Office of Science.

When you use the **AmeriFlux FLUXNET** product, add:

> FLUXNET data products were produced and harmonized by eddy covariance regional
> networks and data processing centers, including AmeriFlux, ChinaFlux, European Fluxes
> Database, ICOS, JapanFlux, KoFlux, OzFlux, SAEON, and TERN. These products also include
> a modified version of ERA5 hourly data provided by the Copernicus Climate Change
> Service.

## Processing references

- AmeriFlux BASE: Chu, H., Christianson, D.S., Cheah, YW. et al. AmeriFlux BASE data
  pipeline to support network growth and data sharing. *Sci Data* 10, 614 (2023).
  https://doi.org/10.1038/s41597-023-02531-2[^chu-2023]
- AmeriFlux FLUXNET and FLUXNET2015: Pastorello, G. et al. The FLUXNET2015 dataset and
  the ONEFlux processing pipeline for eddy covariance data. *Sci Data* 7, 225 (2020).
  https://doi.org/10.1038/s41597-020-0534-3[^pastorello-2020]

## Data availability statement

If your paper has a data availability section, the AmeriFlux policy suggests:

> The AmeriFlux [DATA PRODUCT] were accessed from [SOURCE] on XX Month YYYY

where [SOURCE] can be the AmeriFlux data portal, AmeriFlux APIs, the FLUXNET User
Interface for the Shuttle, or the FLUXNET Shuttle code. Data downloaded through
ameriflux-mcp came through the AmeriFlux APIs.

## What each policy asks of you

| Policy | Obligations |
| --- | --- |
| AmeriFlux CC-BY-4.0 | Cite each site's DOI; include the DOE acknowledgment; informing data providers about publications is recommended. |
| AmeriFlux Legacy | Contact the site PIs when you start in-depth analysis (they may offer co-authorship); cite each DOI; acknowledge site funding; include the DOE "data portal" acknowledgment; inform providers before publication; use the AmeriFlux logo or link in presentations. |
| FLUXNET2015 Tier 1 | CC-BY-4.0: cite each site's DOI and Pastorello et al. (2020). |
| FLUXNET2015 Tier 2 | Scientific and educational use; give data providers at least three weeks to contribute after the first draft. Six sites are Tier 2 only (RU-Sam, RU-SkP, RU-Tks, RU-Vrk, SE-St1, ZA-Kru) and are not part of Pastorello et al. (2020). |

**Mixing escalates.** A study that combines CC-BY-4.0 and Legacy AmeriFlux data follows
the Legacy policy for all of it; one that combines FLUXNET2015 Tier 1 and Tier 2 data
treats all of it as Tier 2. `amf_get_citation` reports the effective policy for the
sites you name, with each obligation marked required or recommended.

## Citing ameriflux-mcp

ameriflux-mcp is software, not a data source: cite the data as above. If you want to
mention the tool, for example in a methods section:

> Data were discovered and retrieved with ameriflux-mcp (idss-mesa, University of New
> Mexico; https://github.com/idss-mesa/ameriflux-mcp), version X.Y.Z.

[^amf-policy]: AmeriFlux Data Policy. <https://ameriflux.lbl.gov/data/data-policy/>
[^fluxnet-policy]: FLUXNET Data Policy. <https://fluxnet.org/data/data-policy/>
[^chu-2023]: Chu et al. (2023), Sci Data 10, 614. <https://doi.org/10.1038/s41597-023-02531-2>
[^pastorello-2020]: Pastorello et al. (2020), Sci Data 7, 225. <https://doi.org/10.1038/s41597-020-0534-3>
