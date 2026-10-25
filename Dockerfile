# ameriflux-mcp — stateless Streamable HTTP deployment image (DESIGN.md D25, D29).
# Over HTTP the server never accepts or uses a download identity, and the download and
# local-file tools do not exist: this image serves discovery, availability, variables,
# citations and BADM only.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
RUN useradd --create-home --uid 10001 ameriflux
COPY --from=build --chown=ameriflux:ameriflux /app /app
USER ameriflux
ENV PATH="/app/.venv/bin:$PATH" \
    AMERIFLUX_MCP_SERVER__TRANSPORT=http \
    AMERIFLUX_MCP_SERVER__BIND_ADDRESS=0.0.0.0 \
    AMERIFLUX_MCP_SERVER__BIND_PORT=8080 \
    AMERIFLUX_MCP_SERVER__LOG_LEVEL=info
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"
CMD ["ameriflux-mcp", "--transport", "http", "--bind-address", "0.0.0.0"]
