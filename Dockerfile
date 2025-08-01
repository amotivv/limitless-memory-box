# Multi-stage build for Limitless to Memory Box Sync Agent
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 syncuser

# Copy Python packages from builder stage to syncuser's directory
COPY --from=builder /root/.local /home/syncuser/.local
RUN chown -R syncuser:syncuser /home/syncuser/.local

# Set working directory
WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY limitless_sync.py ./
COPY health_check.py ./

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs && \
    chown -R syncuser:syncuser /app

# Switch to non-root user
USER syncuser

# Make sure scripts in .local are usable
ENV PATH=/home/syncuser/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python health_check.py || exit 1

# Expose health check port
EXPOSE 8080

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Run the sync agent
CMD ["python", "limitless_sync.py"]
