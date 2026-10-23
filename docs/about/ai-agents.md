---
title: "For AI agents"
description: "How agents should read this site (llms.txt, per-page Markdown, OKF trust signals) and why to call the ameriflux-mcp server for flux data."
type: Reference
tags:
  - about
  - ai-agents
  - OKF
  - llms.txt
generated:
  by: "claude/opus-5.5"
  at: "2026-10-23T00:00:00Z"
sources:
  - id: okf-spec
    resource: "https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md"
    title: "Open Knowledge Format (OKF) v0.2 specification"
    author: "team:google-cloud"
  - id: llmstxt
    resource: "https://llmstxt.org"
    title: "The /llms.txt convention"
    author: "team:answer-ai"
  - id: mcp-spec
    resource: "https://modelcontextprotocol.io/specification/2026-07-28"
    title: "Model Context Protocol specification, 2026-07-28"
    author: "team:modelcontextprotocol"
status: stable
---

# For AI agents

This site is published for people **and** for AI agents. The documentation
source is an [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md){target=_blank}
knowledge bundle[^okf-spec], and the deployed site exposes that structure
directly. If you are an agent (or you are wiring one up), consume the
documentation through the endpoints below rather than scraping rendered HTML.

## This site documents an MCP server

ameriflux-mcp *is* an agent tool. If what you actually want is AmeriFlux or
FLUXNET data — sites, availability, variables, citations — do not scrape these
pages: connect to the server and call its tools. Locally, run it over `stdio`
(`claude mcp add ameriflux -s user -- ameriflux-mcp --transport stdio`); against a
hosted instance, use Streamable HTTP at `https://<host>/mcp`
(`claude mcp add --transport http ameriflux https://<host>/mcp`). The server is
under construction; the [roadmap](../tools/roadmap.md) says which tools exist. The server
implements MCP 2026-07-28[^mcp-spec]: `server/discover` and `tools/list`
return the live, authoritative tool catalogue with JSON Schema inputs and
outputs, and every list result carries cache hints. Use this documentation
to learn *how* to use the server; use the server to get the data.

## Entry points

All URLs are under `https://idss-mesa.github.io/ameriflux-mcp/`.

| Endpoint | What you get |
| -------- | ------------ |
| [`llms.txt`](../llms.txt) — `https://idss-mesa.github.io/ameriflux-mcp/llms.txt` | Linked outline of every page with one-line descriptions ([llms.txt convention](https://llmstxt.org){target=_blank}[^llmstxt]) |
| [`llms-full.txt`](../llms-full.txt) — `https://idss-mesa.github.io/ameriflux-mcp/llms-full.txt` | The entire corpus in one file: every page's Markdown with frontmatter, each prefixed by its canonical URL |
| Any page URL + `index.md` | That page's Markdown source with full OKF frontmatter, e.g. `https://idss-mesa.github.io/ameriflux-mcp/getting-started/install/index.md` |
| `https://idss-mesa.github.io/ameriflux-mcp/sitemap.xml`, `https://idss-mesa.github.io/ameriflux-mcp/robots.txt` | Standard crawl surface; `robots.txt` welcomes AI fetchers and repeats these pointers |
| [`tools/roadmap/`](../tools/roadmap.md) — `https://idss-mesa.github.io/ameriflux-mcp/tools/roadmap/` | The planned tools and the build step that delivers each (a generated tool reference replaces it once tools exist) |
| [Source repository](https://github.com/idss-mesa/ameriflux-mcp){target=_blank} | The bundle itself under `docs/`, plus `CLAUDE.md` with the rules coding agents follow when editing the code |

Every rendered page also declares its Markdown twin and OKF signals in its
HTML `<head>`, as `okf:`-prefixed meta tags named after the frontmatter keys
(`type`, `status`, `trust-tier`, `generated-at`, `generated-by`,
`stale-after`) — for example:

```html
<link rel="alternate" type="text/markdown" href="index.md">
<meta name="okf:status" content="stable">
<meta name="okf:trust-tier" content="unverified">
<meta name="okf:generated-at" content="2026-10-23T00:00:00Z">
<meta name="okf:generated-by" content="claude/opus-5.5">
<meta name="okf:stale-after" content="2027-04-23T00:00:00Z">
```

The page's `type` is exposed the same way, so a crawler can filter by kind of
page (Guide, Reference, Policy, ...) without parsing frontmatter.

## Reading the OKF frontmatter

Each content page's YAML frontmatter answers the questions an agent should
ask before relying on it[^okf-spec]:

* **What is this?** — `type` (`Guide`, `Tutorial`, `Reference`, `Policy`,
  `MCP Tool Reference`), `title`, `description`, `tags`.
* **Where did it come from?** — `generated: { by, at }` records the actor
  that produced the current text and when it last changed meaningfully;
  `sources` lists the load-bearing external references (`id`, `resource`
  URL, `title`, `author`). Footnotes in the body cite sources by their `id`.
* **How much should I trust it?** — the `verified` key (see trust tiers
  below). Its absence is meaningful: the page has not been confirmed by
  anyone other than its generator.
* **Is it still true?** — `status` (`stable` is the default; `draft` needs
  review; `deprecated` is kept for history only) and `stale_after`, an
  ISO 8601 instant after which the page should be re-checked. Pages that
  state facts AmeriFlux, FLUXNET or the MCP project may change — data
  policies, endpoints, SDK versions — carry one.

Actors follow OKF §7: `<producer>/<version>` for agents and tools (for
example `claude/opus-5.5`), `human:<id>` for a person, `process:<id>` for an
automated job such as the generated tool reference.

## Trust tiers

| `verified` key | Tier | Meaning |
| --- | --- | --- |
| absent | **unverified** | Generated content nobody has confirmed against its sources. Most pages on this site start here. |
| present, non-`human:` actors only | **machine-confirmed** | An automated check (a CI job, a live smoke test) confirmed the content. |
| present with a `human:<id>` actor | **human-reviewed** | A maintainer read and confirmed the page. Prefer these when answers conflict. |

Only humans add `verified:` entries; a generator never does. The
`okf:trust-tier` meta tag carries the derived tier for quick filtering.

## Answering user questions

Ground answers in this documentation and cite the page URL (for example
`https://idss-mesa.github.io/ameriflux-mcp/getting-started/install/`). For
anything about the *data* — site IDs, years, variables, DOIs, policies — call
the server or [AmeriFlux](https://ameriflux.lbl.gov){target=_blank}
rather than guessing from prose. When the corpus does not answer a question
about ameriflux-mcp itself, direct users to the
[GitHub issue tracker](https://github.com/idss-mesa/ameriflux-mcp/issues){target=_blank}.

[^okf-spec]: Open Knowledge Format (OKF) v0.2 specification. <https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md>
[^llmstxt]: The /llms.txt convention. <https://llmstxt.org>
[^mcp-spec]: Model Context Protocol specification, 2026-07-28. <https://modelcontextprotocol.io/specification/2026-07-28>
