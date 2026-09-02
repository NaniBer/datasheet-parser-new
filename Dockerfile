# Datasheet Parser API — container image.
# Runtime: FastAPI (uvicorn) that shells out to `python -m src.main` per job.
# Heavy native dep: cadquery-ocp (OCCT) needs a few OpenGL/X11 shared libs.
# Base pinned by digest — readable tag plus immutable content, so a rebuild months from
# now produces the same base (no floating tags in a deployed image). python:3.11-slim as
# resolved on 2026-09-02; bump deliberately.
FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

# OCCT / cadquery runtime shared libraries (headless: no GL server, just the libs).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglu1-mesa \
        libxrender1 \
        libxext6 \
        libsm6 \
        libx11-6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer caches across source changes.
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Fonts for cadquery/OCCT text() — pin numbers, designators, labels. The slim
# base ships no fonts, so makeText() returns a null font and every part fails.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
        fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# App source, then an editable install so `src.*` imports resolve everywhere
# (the API and the `python -m src.main` subprocess both rely on it).
COPY src ./src
RUN pip install --no-cache-dir -e . --no-deps

# Pre-compile to bytecode. Every API job spawns a fresh `python -m src.main`, and in
# Kubernetes the pod runs with a read-only root filesystem — so without __pycache__ baked
# in, each subprocess re-compiles the whole package on every request (silently: Python
# just skips writing .pyc when the tree is unwritable). Compiled here, read at runtime.
RUN python -m compileall -q src

# Jobs write here; mount a volume in production so artifacts survive restarts.
ENV API_JOBS_DIR=/data/api_jobs \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data/api_jobs

# Run as a non-root user. UID *and* GID are pinned explicitly: the Helm chart sets
# runAsUser/runAsGroup 10001 (deployments charts/default/ideeza-ai-datasheet-parser), and
# a bare `useradd -u 10001` lets Debian pick the next free GID (1000) — leaving the
# running process in a different group than the files it owns.
RUN groupadd -g 10001 appuser \
    && useradd -m -u 10001 -g 10001 appuser \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# Container-level healthcheck hits the app's /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)" || exit 1

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
