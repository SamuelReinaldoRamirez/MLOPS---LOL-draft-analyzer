# ──────────────────────────────────────────────────────────────────────────
# LoL Draft Predictor — Web UI (Next.js) production image
#
# Multi-stage build using Next.js `output: 'standalone'`, which traces only
# the dependencies the server actually needs, producing a small runtime image.
#
# NEXT_PUBLIC_API_BASE_URL is a BUILD-time arg: it is inlined into the client
# bundle, so it must be the URL the user's BROWSER uses to reach the API
# (e.g. http://localhost:8000), NOT the compose-internal http://api:8000.
# ──────────────────────────────────────────────────────────────────────────

# ── Build stage ──
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies against the lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

# Inline the browser-facing API base URL into the client bundle at build time.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

COPY . .
RUN npm run build

# ── Runtime stage ──
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as the non-root `node` user shipped with the base image.
USER node

# Standalone output bundles server.js + minimal node_modules. Static assets
# and public/ are not part of the trace and must be copied explicitly.
COPY --chown=node:node --from=builder /app/public ./public
COPY --chown=node:node --from=builder /app/.next/standalone ./
COPY --chown=node:node --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
