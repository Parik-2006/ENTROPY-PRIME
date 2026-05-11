# Multi-stage Nginx Dockerfile
# Builds frontend and serves with Nginx

FROM node:20-alpine AS frontend-builder
WORKDIR /build

ARG VITE_API_URL=/
ENV VITE_API_URL=$VITE_API_URL

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy source
COPY src/ ./src/
COPY public/ ./public/
COPY vite.config.js index.html ./

# Build with Vite
RUN npm run build

# Final Nginx stage
FROM nginx:1.27-alpine

# Remove default nginx config and conf.d directory
RUN rm -rf /etc/nginx/conf.d /etc/nginx/nginx.conf

# Copy custom nginx config
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy built frontend from builder stage
COPY --from=frontend-builder /build/dist /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=2 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:80/index.html || exit 1

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
