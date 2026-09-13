# ===================================================
# Stage 1: Build the Docusaurus static site
# ===================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Dependencies are copied and installed BEFORE the source, so Docker can reuse
# this layer on every build where package-lock.json has not changed -- which is
# most of them. Copying source first would invalidate it on every commit.
COPY package.json package-lock.json* ./

# `npm ci` over `npm install`: installs exactly the lockfile, and is
# substantially faster because it skips dependency resolution.
RUN npm ci --prefer-offline --no-audit --no-fund

COPY . ./

# Docusaurus' webpack build is memory-hungry, but asking for too LARGE a heap is
# its own problem on a small server: with two concurrent builds on 8GB, two
# 2048MB heaps plus the rest is enough to get a build OOM-killed mid-`npm ci`
# with no error text. 1024MB is comfortably above what this site actually needs
# (verified by a local build) and leaves room for a neighbour.
ENV NODE_OPTIONS=--max-old-space-size=1024
RUN npm run build

# ===================================================
# Stage 2: Serve the static output
# ===================================================
FROM nginx:alpine

RUN rm -rf /usr/share/nginx/html/*
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Lets the orchestrator see a failed nginx rather than a container that is "up"
# but serving nothing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
