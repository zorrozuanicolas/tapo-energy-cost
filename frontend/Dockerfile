# Frontend image: the built dashboard, served by nginx, which also forwards /api to the backend.
# Build it with `frontend/` as the context: docker build -t tapo-frontend frontend

# --- Build stage: type check and build the static files ---
# The result is the same for every processor, so this stage runs natively on the building machine.
FROM --platform=$BUILDPLATFORM node:22-alpine AS build

WORKDIR /app
# Only the dependency files, so this layer is rebuilt only when they change.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Written into the JavaScript during the build: changing it means rebuilding. It must match the
# backend's TIMEZONE.
ARG VITE_TIMEZONE=America/Montevideo
ENV VITE_TIMEZONE=$VITE_TIMEZONE
RUN npm run build

# --- Final stage: nginx and the built files, running as an ordinary user ---
FROM nginxinc/nginx-unprivileged:1.30.6-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

# Checks nginx only; the backend has its own health check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/"]
