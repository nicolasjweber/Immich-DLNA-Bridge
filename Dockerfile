FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    AIOHTTP_NO_EXTENSIONS=1

WORKDIR /app

# Install uv for fast, reliable dependency installation
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

# Install dependencies first for optimal Docker layer caching
COPY pyproject.toml ./
RUN uv pip install --system --no-cache "aiohttp>=3.10,<4" "pillow>=10.0,<12" "prometheus-client>=0.20,<1"

# Copy source code and install project
COPY src ./src
RUN uv pip install --system --no-cache -e .

EXPOSE 8200

# SSDP uses UDP port 1900
EXPOSE 1900/udp

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8200/health')" || exit 1

ENTRYPOINT ["immich-dlna"]
