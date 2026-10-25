# Questions for AmeriFlux and FLUXNET support (draft, 2026-10-22)

The project maintainer sends these; an agent never does. Q1 and Q4 block merging the
download tool (build step 7). Record each answer in RESEARCH.md with the date, then
update DESIGN.md if a decision changes.

## To ameriflux-support@lbl.gov

Subject: Third-party MCP client for the AmeriFlux API (ameriflux-mcp)

> Hello AMP team,
>
> We are building ameriflux-mcp (https://github.com/idss-mesa/ameriflux-mcp), an open
> source (MIT) Model Context Protocol server from the University of New Mexico that
> lets AI assistants find AmeriFlux sites, check data availability, describe FP Standard
> and FLUXNET variables, and produce correct citations and acknowledgments. Discovery
> uses only GET requests to `amfcdn.lbl.gov/api` (site_info_display, site_availability,
> data_availability, fp_var, DOI), rate limited to 2 requests per second and cached for
> hours.
>
> We would also like to offer downloads through your logged route, so that PIs are
> notified as they are today. The design: the user configures their own AmeriFlux user
> ID, email, intended use and a description they write themselves; the tool shows them
> the exact text before anything is sent; and only after they confirm does it make one
> `POST /api/v1/data_download` request with that identity, appending
> " [ameriflux-mcp]" to the description as amerifluxr appends " [amerifluxr download]".
> It never builds file URLs itself.
>
> Could you help with these questions?
>
> 1. **(Q1)** Is it acceptable for a third-party client to call `v1/data_download` this
>    way? Is the " [ameriflux-mcp]" description suffix the right way to identify the
>    client, or would you prefer a Referer header or a registered client tag? What does
>    `is_test` do on your side (is a test request still logged or sent to PIs)?
> 2. **(Q2)** Is `user_id` validated against registered accounts? How are LEGACY-policy
>    requests gated for users who are not logged in to the website?
> 3. **(Q3)** Does `data_download` accept `data_product="BIF"`, or is BASE-BADM with
>    `site_ids` AA-Flx/AA-Net the supported route for bulk BADM? Is
>    `data_variant="SUBSET"` still accepted for the FLUXNET (v1.3) product?
> 4. **(Q4)** What is the exact response shape of `data_download`, including error
>    responses? Do the returned URLs expire? The file links end in `?=<user_id>`; our
>    client strips that tag before fetching (the request itself is already logged) so no
>    identity reaches the file server. Would you rather we keep it?
> 5. **(Q5)** Are there rate limits or terms of use for automated GET access to
>    `amfcdn.lbl.gov/api`? Is there a deprecation plan for v1 relative to v2?
>
> Thank you,

## To support@fluxnet.org

Subject: FLUXNET2015 and FLUXNET-CH4 access for a third-party client

> 1. **(Q6)** Does the AmeriFlux `data_download` API accept FLUXNET2015 requests, or is
>    the fluxnet.org form the only supported route? Is the openly indexed
>    `ftp.fluxdata.org/.fluxnet_downloads_67934/paper_test/` directory a sanctioned
>    distribution path? (We do not use it.)
> 2. **(Q7)** May we redistribute tables derived from
>    `webdoc/variable_codes_{FULLSET,SUBSET}_20200504.csv` (variable names, units,
>    descriptions) inside an MIT-licensed package, with attribution? Under what terms?
> 3. **(Q8)** What reference paper should a citation of the FLUXNET-CH4 Community
>    Product V1.0 include alongside each site's 10.18140/FLX DOI?

## Answers

None yet.
