# ===================================================
# Stage 1: Build embeddable web widget bundle
# ===================================================
FROM node:20-alpine AS widget-builder

WORKDIR /widget
COPY widget/package.json widget/package-lock.json* ./
RUN npm install
COPY widget/ ./
RUN npm run build

# ===================================================
# Stage 2: Production Python Backend Container
# ===================================================
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8422 \
    HOST=0.0.0.0

# Install minimal OS build dependencies & curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 -r requirements.txt

# Copy application source & built widget
COPY . .
COPY --from=widget-builder /widget/dist ./widget/dist

# Install commb package in editable/local mode for CLI availability
RUN pip install --no-cache-dir -e .

EXPOSE 8422

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8422}/health || exit 1

CMD ["python", "-m", "app.cli", "start"]
