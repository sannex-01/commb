# ===================================================
# Stage 1: Build the embeddable web widget bundle
# ===================================================
FROM node:20-alpine AS widget-builder

WORKDIR /widget

# Dependencies before source, so this layer is reused whenever the lockfile is
# unchanged. `npm ci` installs the lockfile exactly and skips resolution.
COPY widget/package.json widget/package-lock.json* ./
RUN npm ci --prefer-offline --no-audit --no-fund

COPY widget/ ./
RUN npm run build

# ===================================================
# Stage 2: Compile Python dependencies
# ===================================================
# build-essential is ~363MB and is needed only to COMPILE packages with native
# extensions. Doing that here and copying just the installed result into the
# final stage keeps the compiler out of the shipped image.
FROM python:3.11-slim AS python-builder

ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# A virtualenv gives one self-contained directory to copy across stages.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --default-timeout=1000 --retries=10 -r requirements.txt

# ===================================================
# Stage 3: Runtime
# ===================================================
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8422 \
    HOST=0.0.0.0 \
    PATH="/opt/venv/bin:$PATH"

# curl is for the healthcheck only. No compiler here: anything needing one was
# already built in stage 2.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# The compiled dependencies, without the toolchain that produced them.
COPY --from=python-builder /opt/venv /opt/venv

# The user is created before the COPYs so they can set ownership inline with
# --chown. A `chown -R /app` afterwards would rewrite every file's metadata,
# which Docker stores as a SECOND full copy of the app layer -- doubling the
# image for nothing.
RUN useradd --system --create-home --uid 1001 commb

COPY --chown=commb:commb . .
COPY --from=widget-builder --chown=commb:commb /widget/dist ./widget/dist

# --no-deps: requirements.txt already installed everything, and without this pip
# re-resolves the whole tree against the index on every build.
RUN pip install --no-cache-dir --no-deps -e .

# Run unprivileged: a compromise in the app should not be root in the
# container. The user was created above so the COPYs could use --chown.
USER commb

EXPOSE 8422

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8422}/health || exit 1

CMD ["python", "-m", "app.cli", "start"]
