# Limitless to Memory Box Sync Agent

A production-ready Python application that automatically synchronizes lifelog data from the Limitless Pendant to Memory Box, enabling seamless integration between personal conversation capture and semantic memory storage.

## Features

- **Automated Sync**: Continuous synchronization of new lifelog entries
- **Incremental Processing**: Avoid duplicate processing through state tracking
- **Semantic Enhancement**: Intelligent categorization and rich metadata preservation
- **Production Reliability**: 99%+ uptime with comprehensive error handling
- **Docker Deployment**: Container-ready for local and cloud deployment

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Limitless API key
- Memory Box API credentials
- Mailgun account for notifications

### 1. Clone and Setup

```bash
git clone <repository-url>
cd limitless-memory-box
```

### 2. Configure Environment

Copy the environment template and fill in your credentials:

```bash
cp .env.template .env
```

Edit `.env` with your API keys:

```bash
# Limitless API Configuration
LIMITLESS_API_KEY=your_limitless_api_key_here
LIMITLESS_API_URL=https://api.limitless.ai

# Memory Box API Configuration
MEMORYBOX_API_KEY=your_memorybox_token_here
MEMORYBOX_API_URL=https://memorybox.amotivv.ai
MEMORYBOX_BUCKET=Limitless-Lifelogs

# Email Notifications (Mailgun)
MAILGUN_API_KEY=your_mailgun_api_key_here
MAILGUN_DOMAIN=your-domain.com
ALERT_EMAIL=alerts@your-domain.com
```

### 3. Start the Sync Agent

```bash
docker-compose up -d
```

### 4. Monitor Status

Check the health endpoint:
```bash
curl http://localhost:8080/health
```

View logs:
```bash
docker-compose logs -f limitless-sync
```

## Architecture

The sync agent follows a modular architecture with the following components:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Limitless to Memory Box Sync Agent           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  │   Limitless     │    │   Sync Agent    │    │   Memory Box    │
│  │     API         │◄──►│   (Docker)      │◄──►│     API         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘
│                                 │                                │
│                                 ▼                                │
│                          ┌─────────────────┐                     │
│                          │   SQLite DB     │                     │
│                          │  (Sync State)   │                     │
│                          └─────────────────┘                     │
│                                 │                                │
│                                 ▼                                │
│                          ┌─────────────────┐                     │
│                          │   Mailgun       │                     │
│                          │ (Notifications) │                     │
│                          └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

- **Sync Agent**: Main orchestration logic with scheduling
- **Limitless Client**: Rate-limited API client with circuit breaker
- **Memory Box Client**: Status polling and bucket management
- **Content Processor**: Intelligent categorization and formatting
- **Database Manager**: SQLite-based state tracking
- **Notification Manager**: Email alerts via Mailgun
- **Health Checker**: HTTP endpoints for monitoring

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LIMITLESS_API_KEY` | Limitless API key | Required |
| `MEMORYBOX_API_KEY` | Memory Box API token | Required |
| `MAILGUN_API_KEY` | Mailgun API key | Required |
| `SYNC_INTERVAL_MINUTES` | Sync frequency | 30 |
| `TIMEZONE` | Processing timezone | America/Los_Angeles |
| `LOG_LEVEL` | Logging level | INFO |

### Advanced Configuration

For production deployments, you can customize:

- **Rate Limiting**: `RATE_LIMIT_REQUESTS_PER_MINUTE` (default: 180)
- **Batch Size**: `BATCH_SIZE` (default: 10)
- **Polling**: `MAX_POLL_ATTEMPTS`, `POLL_INTERVAL_SECONDS`
- **Storage**: `DATABASE_PATH`, `LOG_PATH`

## Monitoring

### Health Checks

The agent provides several health check endpoints:

- `GET /health` - Overall health status
- `GET /health/detailed` - Detailed component status
- `GET /ready` - Readiness probe
- `GET /live` - Liveness probe

### Logging

Structured logging with multiple outputs:
- Console output for Docker logs
- File logging in `/app/logs/`
- Separate error log for critical issues

### Email Notifications

Automatic email alerts for:
- Sync errors and failures
- Daily summary reports
- System health issues
- Startup/shutdown notifications

## Development

### Local Development Setup

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.template .env
   # Edit .env with your credentials
   ```

4. **Run locally:**
   ```bash
   python limitless_sync.py
   ```

### Testing

Run health check:
```bash
python health_check.py
```

Test individual components:
```bash
python -m src.limitless_client  # Test Limitless API
python -m src.memorybox_client  # Test Memory Box API
python -m src.notifications     # Test email notifications
```

### Project Structure

```
limitless-memory-box/
├── src/                        # Source code
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── models.py              # Data models
│   ├── database.py            # SQLite database layer
│   ├── rate_limiter.py        # Rate limiting and resilience
│   ├── limitless_client.py    # Limitless API client
│   ├── memorybox_client.py    # Memory Box API client
│   ├── content_processor.py   # Content analysis and formatting
│   ├── notifications.py       # Email notification system
│   ├── health.py              # Health check system
│   └── sync_agent.py          # Main sync orchestration
├── memory-bank/               # Memory Bank documentation
├── limitless_sync.py          # Main entry point
├── health_check.py            # Standalone health check
├── Dockerfile                 # Docker configuration
├── docker-compose.yml         # Docker Compose setup
├── requirements.txt           # Python dependencies
├── .env.template             # Environment template
└── README.md                 # This file
```

## Deployment

### Docker Deployment (Recommended)

1. **Build and start:**
   ```bash
   docker-compose up -d
   ```

2. **Monitor:**
   ```bash
   docker-compose logs -f
   curl http://localhost:8080/health
   ```

3. **Update:**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

### Cloud Deployment

The agent is designed for cloud deployment on:
- AWS EC2 with Docker
- Google Compute Engine
- Azure Virtual Machines
- Any Docker-compatible platform

### Production Considerations

- **Persistent Storage**: Ensure `/app/data` and `/app/logs` are persistent
- **Backup**: Regular backup of SQLite database
- **Monitoring**: Set up external monitoring of health endpoints
- **Log Rotation**: Configure log rotation for long-running deployments
- **Resource Limits**: Adjust memory/CPU limits based on usage

## Troubleshooting

### Common Issues

1. **API Authentication Errors**
   - Verify API keys in `.env` file
   - Check API key permissions and expiration

2. **Sync Failures**
   - Check logs: `docker-compose logs limitless-sync`
   - Verify network connectivity to APIs
   - Check Memory Box bucket exists

3. **Email Notifications Not Working**
   - Verify Mailgun configuration
   - Check domain verification in Mailgun
   - Test with: `python -c "from src.notifications import *; ..."`

4. **High Memory Usage**
   - Adjust batch size: `BATCH_SIZE=5`
   - Increase sync interval: `SYNC_INTERVAL_MINUTES=60`
   - Check for memory leaks in logs

### Debug Mode

Enable debug logging:
```bash
# In .env file
LOG_LEVEL=DEBUG
```

### Database Inspection

Access SQLite database:
```bash
docker exec -it limitless-memory-sync sqlite3 /app/data/limitless_sync.db
```

Useful queries:
```sql
-- Check sync statistics
SELECT * FROM sync_state;

-- View recent syncs
SELECT * FROM synced_lifelogs ORDER BY synced_at DESC LIMIT 10;

-- Check for errors
SELECT * FROM sync_errors ORDER BY occurred_at DESC LIMIT 10;
```

## API Reference

### Health Check Endpoints

- **GET /health**
  - Returns overall health status
  - Status: 200 (healthy) or 503 (unhealthy)

- **GET /health/detailed**
  - Returns detailed component status
  - Includes system metrics and configuration

- **GET /ready**
  - Kubernetes readiness probe
  - Checks if app is ready to serve traffic

- **GET /live**
  - Kubernetes liveness probe
  - Simple alive check

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Check the troubleshooting section
- Review logs for error details
- Open an issue on GitHub

---

**Limitless to Memory Box Sync Agent** - Bridging conversation capture with semantic memory storage.
