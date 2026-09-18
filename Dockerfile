# === Stage 1: Frontend build ===
FROM node:20-slim AS node-builder

WORKDIR /app
COPY . /app

ARG COLLECTION_TYPE=photographs
RUN npm install --omit=dev && \
    npm run setup -- --type=$COLLECTION_TYPE && \
    mkdir -p /build/dist && \
    cp -r src/frontend/$COLLECTION_TYPE/dist/* /build/dist/

# === Stage 2: Python runtime ===
FROM python:3.12-slim

WORKDIR /app

# Searching only encodes short text queries, so the default image carries the
# CPU build of PyTorch, which is several GB smaller than the CUDA build.
# Build with --build-arg TORCH_VARIANT=cu124 for a GPU image to run `ingest` on.
ARG TORCH_VARIANT=cpu
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/${TORCH_VARIANT}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 1000 is the user id Hugging Face Spaces runs containers as.
RUN useradd --create-home --uid 1000 dce && \
    mkdir -p /data /app/.cache && \
    chown dce:dce /data /app/.cache

ENV DCE_DATA_DIR=/data \
    HF_HOME=/app/.cache/huggingface \
    PYTHONUNBUFFERED=1

# Store the model in the image so the container starts without downloading it.
# This runs before the source is copied so that code changes do not repeat it.
ARG PRELOAD_MODEL=true
COPY config.json docker/preload_model.py /tmp/preload/
RUN if [ "$PRELOAD_MODEL" = "true" ]; then \
    cd /tmp/preload && su dce -c "HF_HOME=$HF_HOME python preload_model.py"; \
    fi

COPY . /app

ARG COLLECTION_TYPE=photographs
COPY --from=node-builder /build/dist /app/src/frontend/$COLLECTION_TYPE/dist
COPY --from=node-builder /app/config.json /app/config.json

USER dce

VOLUME /data
EXPOSE 8000

# Loading the model and the index takes a while before the first health check passes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["serve"]
