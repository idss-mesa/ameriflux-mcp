# The ameriflux-mcp download identity

Most of ameriflux-mcp needs no account: finding sites, checking availability, describing
variables, getting citations and previewing local files are anonymous. **Only downloading
data from AmeriFlux** needs an identity.

## Why: downloads are disclosures

AmeriFlux has no API keys. Every download request carries the user's AmeriFlux user ID,
email, an intended-use category and a short description. AmeriFlux sends that information
to the principal investigators (PIs) of each downloaded site and posts it to the AmeriFlux
Data Download Log (visible to logged-in users). Tower teams use it to see who uses their
data and to offer collaboration.

So ameriflux-mcp:

1. reads the identity only from the server's configuration (environment or YAML), never
   from tool arguments: an agent cannot invent or edit it, and **must not** write
   intended-use text for the user;
2. answers a download request first with a **plan** showing the exact text, the sites it
   goes to and the data policy that applies, and sends nothing;
3. sends the request only on a second call with `confirm=true` and `accept_data_policy`
   naming that policy;
4. acts with an identity only on stdio (the user's own machine). A hosted (HTTP) server
   never accepts or uses one.

## Setting it up (the user does this, not the agent)

Create an AmeriFlux/FLUXNET account at https://amfcdn.lbl.gov/create; the username is the
AmeriFlux user ID. Then set, in the environment of the process that starts ameriflux-mcp:

| Variable | Required | Meaning |
| --- | --- | --- |
| `AMERIFLUX_USER_ID` | yes | AmeriFlux username |
| `AMERIFLUX_USER_EMAIL` | yes | Email registered with AmeriFlux |
| `AMERIFLUX_USER_NAME` | no | Name shown to PIs |
| `AMERIFLUX_INTENDED_USE` | yes | 1 synthesis, 2 model, 3 remote sensing, 4 other research, 5 education, 6 other |
| `AMERIFLUX_DESCRIPTION` | yes | 20-1000 characters, in the user's own words |
| `AMERIFLUX_MCP_IDENTITY__IS_TEST` | yes | `true` for test requests, `false` for real downloads; no default |

`AMERIFLUX_MCP_IDENTITY__…` forms of the first five take precedence when set. Look-alike
names (`AMERIFLUX_EMAIL`, `AMERIFLUX_USERNAME`, `AMF_USER_ID`, `AMERIFLUX_TOKEN`,
`AMERIFLUX_API_KEY`) are not read. The repository's `scripts/install.sh --with-identity`
stores them in each agent's server configuration. A YAML config may define named
`identity.profiles` (intended use + description per project), chosen per download with
`profile=`.

## Checking it

Call `amf_ping`: `identity` reports which fields are configured, as booleans and profile
names, never the values. `identity.reason` is `ok`, `incomplete` (user ID or email
missing) or `http` (hosted server: never available). Downloads also refuse until
`isTestSet` is true.

## Errors

- `auth_required` (`details.guide` = this page): no usable identity; `details.reason` says
  which part is missing (`is_test_unset`, a profile without intended use or description).
- `upstream_forbidden`: AmeriFlux refused the download request; check that the user ID and
  email match the account and that the accepted policy applies to the sites.

## Data policy at download time

AmeriFlux sites share data under CC-BY-4.0 or the AmeriFlux Legacy policy; combining them
means Legacy for everything. The AmeriFlux FLUXNET product exists only for CC-BY sites.
FLUXNET2015 uses Tier 1 (CC-BY-4.0) and Tier 2 and is downloaded by the user through
fluxnet.org's login-protected form, which ameriflux-mcp does not automate.
