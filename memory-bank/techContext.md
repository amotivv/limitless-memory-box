# Technical Context - Limitless to Memory Box Sync Agent

## Technology Stack

### Core Technologies
- **Python 3.11**: Main application language
- **asyncio**: Asynchronous programming for concurrent API calls
- **httpx**: Modern async HTTP client for API interactions
- **SQLite**: Lightweight database for sync state management
- **Docker**: Containerization for deployment
- **APScheduler**: Reliable job scheduling for periodic sync

### Key Dependencies (Production)
```python
# Core dependencies
httpx==0.27.0
pydantic==1.10.13  # Using v1 for stability
python-dotenv==1.0.1

# Scheduling
apscheduler==3.10.4

# Email notifications
requests==2.31.0

# Async support
asyncio-mqtt==0.16.1

# Logging and structured data
structlog==23.2.0

# Timezone support (fallback for older Python)
pytz==2023.3

# Health check server
aiohttp==3.9.1

# Development and testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-mock==3.12.0
black==23.11.0
flake8==6.1.0
```

## API Specifications

### Limitless API
- **Base URL**: `https://api.limitless.ai`
- **Authentication**: `X-API-Key` header
- **Rate Limit**: 180 requests/minute
- **Pagination**: Cursor-based with `nextCursor`
- **Key Endpoints**:
  - `GET /v1/lifelogs` - List lifelogs with filtering
  - `GET /v1/lifelogs/{id}` - Get specific lifelog

### Memory Box API
- **Base URL**: Configurable (default: `https://memorybox.amotivv.ai`)
- **Authentication**: `Bearer` token
- **Key Endpoints**:
  - `POST /api/v2/memory` - Create memory
  - `GET /api/v2/memory/{id}/status` - Check processing status
  - `GET /api/v2/buckets` - List buckets
  - `POST /api/v2/buckets` - Create bucket

### Mailgun API
- **Base URL**: `https://api.mailgun.net/v3/{domain}`
- **Authentication**: API key
- **Endpoint**: `POST /messages` - Send email

## Development Environment

### Local Development Setup
```bash
# Python environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Environment configuration
cp .env.template .env
# Edit .env with your API keys

# Run locally
python limitless_sync.py
```

### Docker Development
```bash
# Build image
docker build -t limitless-sync .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f limitless-sync
```

## Configuration Management

### Environment Variables
```bash
# Limitless API Configuration
LIMITLESS_API_KEY=your_limitless_api_key
LIMITLESS_API_URL=https://api.limitless.ai

# Memory Box API Configuration
MEMORYBOX_API_KEY=your_memorybox_token
MEMORYBOX_API_URL=https://memorybox.amotivv.ai
MEMORYBOX_BUCKET=Limitless-Lifelogs

# Email Notifications
MAILGUN_API_KEY=your_mailgun_key
MAILGUN_DOMAIN=your-domain.com
ALERT_EMAIL=alerts@your-domain.com

# Sync Configuration
SYNC_INTERVAL_MINUTES=30
TIMEZONE=America/Los_Angeles
LOG_LEVEL=INFO

# Docker/Deployment
DATABASE_PATH=/app/data/limitless_sync.db
LOG_PATH=/app/logs/
```

### Configuration Validation
```python
from pydantic import BaseSettings, validator

class Config(BaseSettings):
    # API Keys (required)
    limitless_api_key: str
    memorybox_api_key: str
    mailgun_api_key: str
    
    # URLs with defaults
    limitless_api_url: str = "https://api.limitless.ai"
    memorybox_api_url: str = "https://memorybox.amotivv.ai"
    
    # Sync settings with validation
    sync_interval_minutes: int = 30
    batch_size: int = 10
    
    @validator('sync_interval_minutes')
    def validate_sync_interval(cls, v):
        if v < 5 or v > 1440:  # 5 minutes to 24 hours
            raise ValueError('Sync interval must be between 5 and 1440 minutes')
        return v
    
    class Config:
        env_file = '.env'
```

## Database Design

### SQLite Schema
```sql
-- Sync state management
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_sync_time TEXT NOT NULL,
    total_synced INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Individual lifelog tracking
CREATE TABLE synced_lifelogs (
    lifelog_id TEXT PRIMARY KEY,
    memory_box_id INTEGER,
    synced_at TEXT NOT NULL,
    title TEXT,
    start_time TEXT,
    end_time TEXT,
    processing_status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Error tracking and debugging
CREATE TABLE sync_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lifelog_id TEXT,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_details TEXT,
    occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (lifelog_id) REFERENCES synced_lifelogs(lifelog_id)
);

-- Performance metrics
CREATE TABLE sync_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_started_at TEXT NOT NULL,
    sync_completed_at TEXT,
    lifelogs_processed INTEGER DEFAULT 0,
    lifelogs_successful INTEGER DEFAULT 0,
    lifelogs_failed INTEGER DEFAULT 0,
    total_duration_seconds REAL,
    average_processing_time_ms REAL
);

-- Indexes for performance
CREATE INDEX idx_synced_lifelogs_synced_at ON synced_lifelogs(synced_at);
CREATE INDEX idx_synced_lifelogs_status ON synced_lifelogs(processing_status);
CREATE INDEX idx_sync_errors_occurred_at ON sync_errors(occurred_at);
CREATE INDEX idx_sync_metrics_started_at ON sync_metrics(sync_started_at);
```

## Deployment Architecture

### Docker Configuration
```dockerfile
# Multi-stage build for optimization
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY limitless_sync.py ./
COPY health_check.py ./

# Create directories and set permissions
RUN mkdir -p /app/data /app/logs && \
    useradd -m -u 1000 syncuser && \
    chown -R syncuser:syncuser /app

USER syncuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python health_check.py || exit 1

EXPOSE 8080

CMD ["python", "limitless_sync.py"]
```

### Docker Compose
```yaml
version: '3.8'

services:
  limitless-sync:
    build: .
    container_name: limitless-memory-sync
    restart: unless-stopped
    environment:
      - DATABASE_PATH=/app/data/limitless_sync.db
      - LOG_PATH=/app/logs/
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "python", "health_check.py"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Security Considerations

### API Key Management
- Store API keys in environment variables only
- Never commit API keys to version control
- Use Docker secrets in production environments
- Rotate API keys regularly

### Network Security
- Use HTTPS for all API communications
- Validate SSL certificates
- Implement request timeouts
- Use connection pooling with limits

### Data Security
- Encrypt sensitive data in database
- Use secure file permissions for SQLite database
- Implement proper logging without exposing secrets
- Regular security updates for dependencies

## Performance Considerations

### Rate Limiting
- Implement token bucket algorithm for Limitless API
- Exponential backoff for failed requests
- Respect API rate limit headers
- Queue requests during high-traffic periods

### Memory Management
- Stream large API responses
- Limit concurrent operations
- Clean up database periodically
- Monitor memory usage in container

### Database Optimization
- Use appropriate indexes
- Implement connection pooling
- Regular VACUUM operations
- Archive old sync data

## Monitoring and Observability

### Logging Strategy
```python
import structlog

logger = structlog.get_logger()

# Structured logging with context
logger.info(
    "sync_completed",
    sync_id=sync_id,
    duration_seconds=duration,
    lifelogs_processed=count,
    success_rate=success_rate
)
```

### Health Checks
- Database connectivity
- API endpoint availability
- Recent sync activity
- Disk space and memory usage

### Metrics Collection
- Sync success/failure rates
- API response times
- Processing durations
- Error frequencies and types

## Testing Strategy

### Unit Tests
```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_sync_new_lifelogs():
    # Mock API responses
    with patch('limitless_client.fetch_lifelogs') as mock_fetch:
        mock_fetch.return_value = [mock_lifelog]
        
        sync_agent = SyncAgent(config)
        result = await sync_agent.sync_lifelogs()
        
        assert result.success_count == 1
        assert result.error_count == 0
```

### Integration Tests
- Test with real API endpoints (using test accounts)
- Validate database operations
- Test Docker container health
- End-to-end sync workflow testing

### Load Testing
- Simulate high-volume lifelog processing
- Test rate limiting behavior
- Validate memory usage under load
- Test recovery from API failures
