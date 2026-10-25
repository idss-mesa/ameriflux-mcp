# Getting FLUXNET2015 data

FLUXNET2015 (212 sites, frozen, labelled "outdated" by fluxnet.org in favour of the
FLUXNET Shuttle) is discoverable here without an account: `amf_search_sites`,
`amf_get_site`, `amf_get_availability` and `amf_get_citation` all cover it. Its data
files are not downloaded by this server.

## Why not

The download form on fluxnet.org needs a fluxnet.org account and sends your intended use
to the data producers. ameriflux-mcp never automates that login and never uses
unofficial copies of the files (such as open directory listings on the file server):
they bypass the record that tells site teams who uses their data.

## How

1. Sign in at https://fluxnet.org and request the FULLSET or SUBSET zips of the sites
   you need ("Download Data" → FLUXNET2015).
2. Put the zips, unopened, in one folder, for example `~/fluxnet2015`.
3. Add that folder to the server's local roots and restart the server:
   `AMERIFLUX_MCP_LOCAL__ROOTS=~/fluxnet2015` (environment; separate several folders
   with commas) or, in the YAML configuration, `local: {roots: [~/fluxnet2015]}`.
4. `amf_list_files(family=['fluxnet2015'])` lists them;
   `amf_preview_data(site='US-Ha1', product='FLUXNET2015', resolution='DD')` reads one
   inside its zip.

## Before you publish

FLUXNET2015 data follow the CC-BY-4.0 (Tier One) or Tier Two policy. Any Tier Two site
(RU-Sam, RU-SkP, RU-Tks, RU-Vrk, SE-St1, ZA-Kru) makes the whole synthesis Tier Two:
contact the providers when you begin, and give them three weeks after the first draft.
`amf_get_citation(sites=[...], product='FLUXNET2015')` returns the citations and the
obligations; `ameriflux://guide/data-policy` explains them.
