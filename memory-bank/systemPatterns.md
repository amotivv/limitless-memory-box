# System Patterns - Limitless to Memory Box Sync Agent

## Architecture Overview

### High-Level Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Limitless     │    │   Sync Agent    │    │   Memory Box    │
│     API         │◄──►│   (Docker)      │◄──►│     API         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   SQLite DB     │
                       │  (Sync State)   │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Mailgun       │
                       │ (Notifications) │
                       └─────────────────┘
```

### Component Architecture
```
Sync Agent Container
├── Main Process (limitless_sync.py)
├── Limitless Client (API + Rate Limiting)
├── Memory Box Client (API + Status Polling)
├── Content Processor (Categorization + Formatting)
├── Database Manager (SQLite + Sync State)
├── Notification Manager (Mailgun + Alerts)
└── Health Check Endpoint (Docker Health)
```

## Core Design Patterns

### 1. Incremental Sync Pattern
**Problem**: Avoid reprocessing already-synced lifelogs
**Solution**: Track sync state in local SQLite database

```python
class SyncState:
    - last_sync_timestamp
    - processed_lifelog_ids
    - sync_statistics
    
def incremental_sync():
    last_sync = get_last_sync_time()
    new_lifelogs = fetch_lifelogs_since(last_sync)
    for lifelog in new_lifelogs:
        if not is_already_synced(lifelog.id):
            process_lifelog(lifelog)
```

### 2. Rate Limiting Pattern
**Problem**: Limitless API has 180 requests/minute limit
**Solution**: Token bucket algorithm with exponential backoff

```python
class RateLimiter:
    - tokens: 180
    - refill_rate: 3 tokens/second
    - last_refill: timestamp
    
def make_request():
    if not has_tokens():
        wait_for_tokens()
    consume_token()
    return api_call()
```

### 3. Processing Status Polling Pattern
**Problem**: Memory Box processes memories asynchronously
**Solution**: Poll status endpoint until completion

```python
async def create_memory_with_polling(content):
    memory_id = await create_memory(content)
    
    for attempt in range(max_attempts):
        status = await get_memory_status(memory_id)
        if status == "processed":
            return memory_id
        elif status == "failed":
            raise ProcessingError()
        await sleep(poll_interval)
```

### 4. Circuit Breaker Pattern
**Problem**: API failures can cascade and overwhelm services
**Solution**: Fail fast when services are unavailable

```python
class CircuitBreaker:
    states: CLOSED, OPEN, HALF_OPEN
    failure_threshold: 5
    recovery_timeout: 60s
    
def api_call():
    if circuit_breaker.is_open():
        raise ServiceUnavailable()
    
    try:
        result = make_api_call()
        circuit_breaker.record_success()
        return result
    except Exception:
        circuit_breaker.record_failure()
        raise
```

## Data Flow Patterns

### 1. Sync Pipeline
```
Limitless API → Content Analysis → Memory Box API → Status Polling → Database Update
```

### 2. Error Handling Flow
```
API Error → Retry Logic → Circuit Breaker → Email Alert → Database Log
```

### 3. Content Processing Flow
```
Raw Lifelog → Speaker Extraction → Categorization → Formatting → Reference Data → Memory Box
```

## Persistence Patterns

### SQLite Schema Design
```sql
-- Sync state tracking
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY,
    last_sync_time TEXT,
    total_synced INTEGER
);

-- Individual lifelog tracking
CREATE TABLE synced_lifelogs (
    lifelog_id TEXT PRIMARY KEY,
    memory_box_id INTEGER,
    synced_at TEXT,
    title TEXT,
    start_time TEXT,
    processing_status TEXT
);

-- Error tracking
CREATE TABLE sync_errors (
    id INTEGER PRIMARY KEY,
    lifelog_id TEXT,
    error_message TEXT,
    error_time TEXT,
    retry_count INTEGER
);
```

## Integration Patterns

### Memory Box API Integration
```python
# Follow MCP server patterns for consistency
payload = {
    "raw_content": formatted_content,
    "bucketId": "Limitless-Lifelogs",
    "source_type": "application_plugin",
    "reference_data": {
        "source": {
            "platform": "limitless_pendant",
            "type": "application_plugin",
            "version": "1.0"
        },
        "content_context": {
            "additional_context": {
                "lifelog_id": entry.id,
                "speakers": speakers,
                "conversation_type": category
            }
        }
    }
}
```

### Limitless API Integration
```python
# Respect pagination and rate limits
params = {
    "timezone": config.timezone,
    "start": last_sync_time,
    "limit": batch_size,
    "direction": "asc",
    "includeContents": "true"
}

while has_more_pages:
    response = await rate_limited_request("/v1/lifelogs", params)
    process_batch(response.data.lifelogs)
    params["cursor"] = response.meta.lifelogs.nextCursor
```

## Deployment Patterns

### Container Health Checks
```python
# Health check endpoint
@app.route('/health')
def health_check():
    checks = {
        "database": check_database_connection(),
        "limitless_api": check_limitless_api(),
        "memory_box_api": check_memory_box_api(),
        "last_sync": check_recent_sync()
    }
    
    if all(checks.values()):
        return {"status": "healthy", "checks": checks}, 200
    else:
        return {"status": "unhealthy", "checks": checks}, 503
```

### Graceful Shutdown
```python
def signal_handler(signum, frame):
    logger.info("Received shutdown signal, finishing current sync...")
    sync_agent.stop_gracefully()
    database.close_connections()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
```

## Monitoring Patterns

### Structured Logging
```python
logger.info("sync_started", extra={
    "sync_id": sync_id,
    "last_sync_time": last_sync_time,
    "expected_new_entries": estimated_count
})

logger.info("lifelog_processed", extra={
    "lifelog_id": entry.id,
    "memory_box_id": memory_id,
    "processing_time_ms": processing_time,
    "category": conversation_type
})
```

### Metrics Collection
```python
class SyncMetrics:
    - total_synced: Counter
    - sync_duration: Histogram
    - api_errors: Counter
    - processing_failures: Counter
    
def record_sync_completion(duration, success_count, error_count):
    metrics.sync_duration.observe(duration)
    metrics.total_synced.inc(success_count)
    metrics.processing_failures.inc(error_count)
