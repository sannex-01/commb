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

# Docusaurus' webpack build is memory-hungry and the default heap is what makes
# it fail on a small server, usually with an unhelpful exit code.
ENV NODE_OPTIONS=--max-old-space-size=2048
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
