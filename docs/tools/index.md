# Tools

The generated reference of the tools in this build, and the roadmap of the twelve planned tools.

* [Tool reference](reference.md) - Every ameriflux-mcp tool with its inputs, result fields, upstream endpoints and annotations, generated from the tool registry.
* [Discovery and availability](discovery.md) - Find flux tower sites with amf_search_sites, read one with amf_get_site, and check which years exist per product and policy with amf_get_availability.
* [Variables](variables.md) - Find and decode AmeriFlux BASE and FLUXNET variable names with amf_search_variables and amf_describe_variables: qualifiers, units per resolution, QC, heights.
* [Citations and BADM](citation.md) - Cite AmeriFlux and FLUXNET2015 sites with amf_get_citation (versioned text, policy obligations, acknowledgments) and read site metadata with amf_get_badm.
* [Downloads](downloads.md) - Download AmeriFlux BASE-BADM, FLUXNET and bulk BADM with amf_download_data: a plan first, consent with confirm=true, verified files and sidecars.
* [Local files](local-files.md) - Find, preview and read AmeriFlux and FLUXNET files on your computer with amf_list_files, amf_preview_data and amf_read_bif, inside their zips and offline.
* [Prompts, resources and status](prompts-and-resources.md) - The three ameriflux-mcp prompts, the guide and reference resources agents read, the site card template, and the amf_ping status report.
* [Roadmap](roadmap.md) - The twelve planned ameriflux-mcp tools, the build step that delivers each, and which work over HTTP or need a download identity.
