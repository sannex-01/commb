# ===================================================
# Stage 1: Build Docusaurus Static Site
# ===================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency specifications
COPY package.json package-lock.json* ./

# Install dependencies (ignoring scripts if any)
RUN npm install

# Copy source code and build
COPY . ./
RUN npm run build

# ===================================================
# Stage 2: Production Web Server (NGINX Alpine)
# ===================================================
FROM nginx:alpine

# Remove default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy built static documentation
COPY --from=builder /app/build /usr/share/nginx/html

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
