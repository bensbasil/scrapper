# ==============================================================================
# Production Dockerfile for Business Opportunity Intelligence Platform Dashboard
# Next.js 16 (App Router) / Standalone Output / Non-root Alpine execution
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Base Node Image
# ------------------------------------------------------------------------------
FROM node:20-alpine AS base

# Install libc6-compat for compatibility with native binaries in Alpine
RUN apk add --no-cache libc6-compat

WORKDIR /app

# ------------------------------------------------------------------------------
# 2. Dependencies Stage
# ------------------------------------------------------------------------------
FROM base AS deps

# Copy package descriptors and lockfile
COPY package.json package-lock.json ./

# Install exact dependencies according to package-lock.json
RUN npm ci

# ------------------------------------------------------------------------------
# 3. Builder Stage
# ------------------------------------------------------------------------------
FROM base AS builder

WORKDIR /app

# Copy installed node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy application source code (excluded items filtered by .dockerignore)
COPY . .

# Disable Next.js telemetry during build
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

# Build Next.js application in standalone mode
RUN npm run build

# ------------------------------------------------------------------------------
# 4. Production Runtime Stage
# ------------------------------------------------------------------------------
FROM base AS runner

WORKDIR /app

# Production environment variables
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Create dedicated unprivileged non-root user and group
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy public static assets and standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Set correct user for execution
USER nextjs

# Expose standard application port
EXPOSE 3000

# Container liveness health check using built-in Busybox wget
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

# Production startup command
CMD ["node", "server.js"]
