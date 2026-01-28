FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Install wget for healthcheck
RUN apk add --no-cache wget

# Copy source code
COPY . .

# Create non-root user (use different GID/UID if 1000 is already taken)
# Try GID 1000 first, fall back to 1001 if it exists
RUN if ! addgroup -g 1000 appuser 2>/dev/null; then \
        addgroup -g 1001 appuser && \
        adduser -D -u 1001 -G appuser appuser; \
    else \
        adduser -D -u 1000 -G appuser appuser; \
    fi && \
    chown -R appuser:appuser /app
USER appuser

# Expose Vite dev server port
EXPOSE 5173

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5173 || exit 1

# Start Vite dev server
# Host 0.0.0.0 allows connections from outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

