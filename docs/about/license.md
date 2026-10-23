---
title: "License"
description: "ameriflux-mcp code is MIT-licensed by the Regents of the University of New Mexico; these docs are CC-BY 4.0; flux data carry their own policies."
type: Policy
tags:
  - about
  - license
  - MIT
  - CC-BY
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: ameriflux-mcp-license
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/LICENSE"
    title: "ameriflux-mcp LICENSE file (MIT)"
    author: "team:idss-mesa"
  - id: mit
    resource: "https://opensource.org/license/mit"
    title: "The MIT License"
    author: "team:opensource-org"
  - id: cc-by-4
    resource: "https://creativecommons.org/licenses/by/4.0/"
    title: "Creative Commons Attribution 4.0 International (CC BY 4.0)"
    author: "team:creativecommons"
  - id: amf-policy
    resource: "https://ameriflux.lbl.gov/data/data-policy/"
    title: "AmeriFlux Data Policy"
    author: "team:ameriflux"
status: stable
---

# License

Three things meet on this site: the server software, the documentation you are reading,
and the AmeriFlux and FLUXNET data the server gives access to. Each has its own terms.

## Server code — MIT

The ameriflux-mcp source code (the `ameriflux_mcp` Python package, the `ameriflux-mcp`
command-line program, tests and build scripts) is released under the
[MIT License](https://opensource.org/license/mit){target=_blank}[^mit]:

> Copyright (c) 2026 The Regents of the University of New Mexico

The full text is in the repository's
[`LICENSE`](https://github.com/idss-mesa/ameriflux-mcp/blob/main/LICENSE){target=_blank}
file[^ameriflux-mcp-license]. In short: you may use, copy, modify, merge, publish,
distribute, sublicense and sell the software, provided the copyright notice and
permission notice are included; the software is provided "as is", without warranty.
Code and data that ameriflux-mcp ports from other projects (amerifluxr, the FLUXNET
Shuttle, ONEFlux) keep their own BSD-style licenses and are credited in the repository's
[`NOTICE`](https://github.com/idss-mesa/ameriflux-mcp/blob/main/NOTICE){target=_blank}
file.

## Documentation text — CC-BY 4.0

The prose, tables and examples on this site (everything under `docs/` in the repository,
including the OKF frontmatter) are licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/){target=_blank}[^cc-by-4].
You may share and adapt the material for any purpose, provided you give appropriate
credit ("ameriflux-mcp documentation, idss-mesa / The Regents of the University of New
Mexico, CC-BY 4.0") and indicate whether changes were made. Code snippets embedded in the
documentation may alternatively be used under the MIT terms above. Quoted data-policy
text belongs to AmeriFlux and FLUXNET.

## Flux data — per site and product

Data retrieved through ameriflux-mcp are not part of this project and are not covered by
either license above. Each AmeriFlux site shares its data under the CC-BY-4.0 license or
the AmeriFlux Legacy policy, and FLUXNET2015 under Tier 1 (CC-BY-4.0) or Tier 2[^amf-policy].
Follow the policy of every site you use, and cite it as described in
[Citing AmeriFlux and FLUXNET data](citing-ameriflux.md).

## Trademarks and affiliation

ameriflux-mcp is an independent project of
[idss-mesa](https://github.com/idss-mesa){target=_blank} at the University of New
Mexico. It is not developed, endorsed or supported by the AmeriFlux Management Project,
Lawrence Berkeley National Laboratory, FLUXNET or the U.S. Department of Energy. Their
names belong to their respective owners; this site uses its own original artwork.

[^mit]: The MIT License. <https://opensource.org/license/mit>
[^ameriflux-mcp-license]: ameriflux-mcp `LICENSE` file. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/LICENSE>
[^cc-by-4]: Creative Commons Attribution 4.0 International. <https://creativecommons.org/licenses/by/4.0/>
[^amf-policy]: AmeriFlux Data Policy. <https://ameriflux.lbl.gov/data/data-policy/>
