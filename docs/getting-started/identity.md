---
title: "Download identity"
description: "What AmeriFlux downloads disclose, how to create an account, and how to give ameriflux-mcp your user ID, email and intended use."
type: Guide
tags:
  - getting-started
  - identity
  - downloads
  - data-policy
  - privacy
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: amf-policy
    resource: "https://ameriflux.lbl.gov/data/data-policy/"
    title: "AmeriFlux Data Policy"
    author: "team:ameriflux"
  - id: amf-account
    resource: "https://amfcdn.lbl.gov/create"
    title: "FLUX User Account Creation (AmeriFlux and FLUXNET)"
    author: "team:ameriflux"
  - id: fluxnet-policy
    resource: "https://fluxnet.org/data/data-policy/"
    title: "FLUXNET Data Policy"
    author: "team:fluxnet"
  - id: research
    resource: "https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md"
    title: "ameriflux-mcp verified research (section 5, downloads)"
    author: "team:idss-mesa"
status: draft
stale_after: "2027-04-23T00:00:00Z"
---

# Download identity

Most of ameriflux-mcp needs no account at all: finding sites, checking which years
exist, describing variables, getting citations and previewing files you already have
all work anonymously. Only **downloading data from AmeriFlux** needs an identity, and
this page explains why, what is disclosed, and how to configure it.

!!! info "Available from build step 7"

    The download tool (`amf_download_data`) is the seventh build step, and it ships only
    once AmeriFlux confirms that third-party clients may use its download request. Until
    then you can store an identity with the installer, but nothing uses it.

## What a download discloses, and to whom

AmeriFlux has no API keys. Every download is a request that carries your AmeriFlux user
ID, your email, an intended-use category and a short description of how you will use
the data. AmeriFlux sends that information to the **principal investigators (PIs) of
each site** you download, and posts it to the AmeriFlux Data Download Log (visible to
logged-in users)[^amf-policy]. This is how tower teams learn who uses their data and
offer collaboration, so the text should be accurate and written by you.

ameriflux-mcp therefore follows four rules:

1. **Your words, not the model's.** The identity, intended use and description come only
   from configuration you wrote. They are never tool arguments, so an AI agent cannot
   invent or edit them. The server appends ` [ameriflux-mcp]` to the description so
   AmeriFlux can see which client sent the request.
2. **See it first.** A download request first returns a *plan*: the exact text that will
   be sent, the sites it goes to, and the data policy that applies. Nothing is sent.
3. **Then confirm.** Only a second call with `confirm=true`, naming the data policy you
   accept, sends the request.
4. **Only on your machine.** The download tool exists only over stdio, on the computer
   where your agent runs. A hosted (HTTP) ameriflux-mcp never accepts an identity.

ameriflux-mcp never builds download links itself and never uses unofficial mirrors: every
file comes through AmeriFlux's logged route, so PIs are notified as they are for
downloads from the AmeriFlux website.

## Create an AmeriFlux account

AmeriFlux and FLUXNET share one account system. Create an account on the
[FLUX User Account Creation](https://amfcdn.lbl.gov/create){target=_blank} page[^amf-account]:
full name, institution, email, and a **username**. The username is your AmeriFlux user
ID. The same page links to username lookup and password reset.

A registered account matters most for data under the **AmeriFlux Legacy** policy: the
AmeriFlux website offers Legacy data only to logged-in users. Whether AmeriFlux's API
checks the user ID against registered accounts has not been confirmed yet[^research] (question Q2
in the project's [support questions](https://github.com/idss-mesa/ameriflux-mcp/blob/main/research/questions.md){target=_blank}).

## The settings

| Setting | Environment variable | Required | Notes |
| --- | --- | --- | --- |
| User ID | `AMERIFLUX_USER_ID` | yes | Your AmeriFlux username. |
| Email | `AMERIFLUX_USER_EMAIL` | yes | The email registered with AmeriFlux. |
| Name | `AMERIFLUX_USER_NAME` | no | Shown to PIs alongside your email. |
| Intended use | `AMERIFLUX_INTENDED_USE` | yes | A code from the table below. |
| Description | `AMERIFLUX_DESCRIPTION` | yes | 20–1000 characters, in your own words. |
| Test requests | `AMERIFLUX_MCP_IDENTITY__IS_TEST` | yes | `true` or `false`; no default (see [below](#is_test)). |

Each also has a namespaced form (`AMERIFLUX_MCP_IDENTITY__USER_ID`, …) that wins when
both are set, for giving ameriflux-mcp a different identity from other AmeriFlux tools
that read the plain names. Look-alike names such as `AMERIFLUX_EMAIL`,
`AMERIFLUX_USERNAME`, `AMF_USER_ID`, `AMERIFLUX_TOKEN` or `AMERIFLUX_API_KEY` are
**not** read; the server warns if one is set.

**Intended use.** The six categories AmeriFlux's download form offers:

| Code | Key | Category sent to AmeriFlux |
| --- | --- | --- |
| 1 | `synthesis` | Research - Multi-site synthesis |
| 2 | `model` | Research - Land model/Earth system model |
| 3 | `remote_sensing` | Research - Remote sensing |
| 4 | `other_research` | Research - Other |
| 5 | `education` | Education (Teacher or Student) |
| 6 | `other` | Other |

**Profiles.** One description rarely fits every project. A YAML configuration file can
define named profiles, each with its own intended use and description, and a download
picks one with `profile="…"`; the environment variables above define the `default`
profile:

```yaml
# ameriflux-mcp.yaml — pass with: ameriflux-mcp --config ameriflux-mcp.yaml
identity:
  profiles:
    default:
      intended_use: other_research
      description: "Comparing drought responses of semi-arid grassland GPP across New Mexico towers."
    teaching:
      intended_use: education
      description: "Classroom exercises on energy-balance closure for an ecosystem ecology course."
```

Keep the user ID and email in the environment rather than in a file you might share.

### is_test

AmeriFlux's download request has an `is_test` flag. The AmeriFlux website sends `false`
for real downloads; other clients behave differently, and exactly what AmeriFlux does
with test requests (whether they are logged or sent to PIs) is not documented yet.
ameriflux-mcp therefore gives it **no default**: until you set
`AMERIFLUX_MCP_IDENTITY__IS_TEST` to `true` (trying things out) or `false` (real
downloads for your work), the download tool refuses with `auth_required` and
`reason: is_test_unset`.

## Give it to ameriflux-mcp

=== "Install script"

    ```bash
    scripts/install.sh --with-identity
    ```

    The script reads the variables from your environment or asks for each missing one,
    validates them, and stores them in every agent's server `env`, with owner-only file
    permissions. See [Install](install.md#the-download-identity-and-the-script).

=== "Claude Code"

    ```bash
    claude mcp add ameriflux -s user \
      -e AMERIFLUX_USER_ID=your-username \
      -e AMERIFLUX_USER_EMAIL=you@example.edu \
      -e AMERIFLUX_INTENDED_USE=4 \
      -e AMERIFLUX_DESCRIPTION="Comparing drought responses of semi-arid grassland GPP." \
      -e AMERIFLUX_MCP_IDENTITY__IS_TEST=false \
      -- ameriflux-mcp
    ```

=== "JSON clients"

    ```json
    {
      "mcpServers": {
        "ameriflux": {
          "command": "/ABSOLUTE/PATH/TO/ameriflux-mcp",
          "args": [],
          "env": {
            "AMERIFLUX_USER_ID": "your-username",
            "AMERIFLUX_USER_EMAIL": "you@example.edu",
            "AMERIFLUX_INTENDED_USE": "4",
            "AMERIFLUX_DESCRIPTION": "Comparing drought responses of semi-arid grassland GPP.",
            "AMERIFLUX_MCP_IDENTITY__IS_TEST": "false"
          }
        }
      }
    }
    ```

Check it with `ameriflux-mcp --check` or by asking your agent to call `amf_ping`: the
result says which fields are configured, as booleans and profile names, never the values.

## Data policy at download time

Every AmeriFlux site shares its data under the **CC-BY-4.0** license or the more
restrictive **AmeriFlux Legacy** policy, and combining the two means following Legacy
for everything[^amf-policy]. FLUXNET2015 uses Tier 1 (CC-BY-4.0) and Tier 2[^fluxnet-policy].
The download plan states the policy that applies to the sites you chose, and
`confirm=true` must name it (`accept_data_policy="CCBY4.0"` or `"LEGACY"`), so you
accept the right terms. The AmeriFlux FLUXNET product exists only for CC-BY sites.
[Citing AmeriFlux and FLUXNET data](../about/citing-ameriflux.md) lists what each
policy asks of you.

## FLUXNET2015

FLUXNET2015 files are downloaded through a login-protected form on fluxnet.org that
also asks for an intended-use statement. ameriflux-mcp does not automate that form.
Download the zips yourself, put them in your download directory or a folder listed in
`local.roots` ([Configuration](configuration.md)), and the local file tools read them.

## Privacy

Your identity values are masked in logs, `--print-config` output and the installer's
output, and never written to caches, download records or test fixtures. ameriflux-mcp
also strips the contact emails of tower teams and DOI contributors from its results
unless you explicitly ask for contacts **and** the operator enabled
`privacy.allow_contact_emails` (off by default), for example to contact PIs as the
Legacy policy asks.

[^amf-policy]: AmeriFlux Data Policy. <https://ameriflux.lbl.gov/data/data-policy/>
[^amf-account]: FLUX User Account Creation. <https://amfcdn.lbl.gov/create>
[^fluxnet-policy]: FLUXNET Data Policy. <https://fluxnet.org/data/data-policy/>
[^research]: ameriflux-mcp verified research. <https://github.com/idss-mesa/ameriflux-mcp/blob/main/RESEARCH.md>
