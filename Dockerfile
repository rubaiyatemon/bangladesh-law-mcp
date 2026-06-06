# ── Bangladesh Law MCP Server ──────────────────────────────────────────────
# Multi-stage build:
#   1. Clone the Bangladesh-Legal-Acts-Dataset (with Git LFS) into a
#      throwaway stage so the repo metadata doesn't bloat the final image.
#   2. Copy only the JSON act files into the runtime image.
# ──────────────────────────────────────────────────────────────────────────

# ---------- stage 1: fetch dataset ----------
FROM python:3.12-slim AS fetcher

RUN apt-get update \
 && apt-get install -y --no-install-recommends git git-lfs \
 && git lfs install \
 && git clone --depth 1 \
        https://github.com/sakhadib/Bangladesh-Legal-Acts-Dataset.git \
        /tmp/dataset \
 && git -C /tmp/dataset lfs pull \
 && apt-get purge -y git git-lfs \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# ---------- stage 2: runtime ----------
FROM python:3.12-slim

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .

# Copy the dataset from the fetcher stage
COPY --from=fetcher /tmp/dataset/Data/acts /app/dataset/Data/acts

# Tell the server where the acts live and use HTTP transport
ENV BLA_DATA_DIR=/app/dataset/Data/acts
ENV TRANSPORT=http
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

# Health check — Fly.io hits this to decide if the VM is healthy.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["python", "server.py"]
