# ── Bangladesh Law MCP Server ──────────────────────────────────────────────
# Two-stage build:
#   1. Shallow-clone the Bangladesh-Legal-Acts-Dataset (no LFS) — the JSON
#      files we need are regular git objects, not LFS pointers, so this
#      works without `git lfs install` and without GitHub auth.
#   2. Copy only the JSON act files into the runtime image.
# ──────────────────────────────────────────────────────────────────────────

# ---------- stage 1: fetch dataset ----------
FROM python:3.12-slim AS fetcher

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && git clone --depth 1 --no-checkout \
        https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset.git \
        /tmp/dataset \
 && git -C /tmp/dataset sparse-checkout init --cone \
 && git -C /tmp/dataset sparse-checkout set acts \
 && git -C /tmp/dataset checkout \
 && mkdir -p /tmp/dataset-out/acts \
 && cp -r /tmp/dataset/acts/. /tmp/dataset-out/acts/ \
 && apt-get purge -y git \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* /tmp/dataset

# ---------- stage 2: runtime ----------
FROM python:3.12-slim

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .

# Copy the dataset from the fetcher stage.
# The server expects files matching acts/act-print-*.json
# and BLA_DATA_DIR pointing at the parent of the JSON files.
COPY --from=fetcher /tmp/dataset-out/acts /app/dataset/acts

# Tell the server where the acts live and use HTTP transport
ENV BLA_DATA_DIR=/app/dataset/acts
ENV TRANSPORT=http
ENV HOST=0.0.0.0
ENV PORT=8000
# Keep startup logs on so Render's "Logs" tab shows progress
ENV BLA_LOG_LEVEL=INFO
# Python prints should be flushed immediately to container stdout
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check — Render hits this to decide if the instance is healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["python", "server.py"]
