# Database Maintenance Guide - Limitless to Memory Box Sync Agent

This guide provides comprehensive SQLite database maintenance commands for managing the sync agent's state and troubleshooting issues.

## Table of Contents
- [Quick Reference](#quick-reference)
- [Database Schema Overview](#database-schema-overview)
- [Status Monitoring](#status-monitoring)
- [Sync State Management](#sync-state-management)
- [Lifelog Management](#lifelog-management)
- [Error Management](#error-management)
- [Performance Maintenance](#performance-maintenance)
- [Backup and Recovery](#backup-and-recovery)
- [Troubleshooting Scenarios](#troubleshooting-scenarios)

## Quick Reference

### Basic Connection
```bash
# Connect to database
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db

# Run single command
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "YOUR_SQL_COMMAND_HERE"
```

### Most Common Commands
```bash
# Check sync status
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "SELECT id, last_sync_time, total_synced FROM sync_state;"

# Count synced lifelogs
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "SELECT COUNT(*) as total_lifelogs FROM synced_lifelogs;"

# View recent syncs
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "SELECT lifelog_id, title, synced_at, processing_status FROM synced_lifelogs ORDER BY synced_at DESC LIMIT 10;"
```

## Database Schema Overview

The sync agent uses four main tables:

### 1. sync_state
Tracks overall sync status and timestamps.
```sql
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_sync_time TEXT NOT NULL,
    total_synced INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### 2. synced_lifelogs
Tracks individual lifelog processing status.
```sql
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
```

### 3. sync_errors
Logs sync errors for debugging.
```sql
CREATE TABLE sync_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lifelog_id TEXT,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_details TEXT,
    occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
```

### 4. sync_metrics
Tracks performance metrics.
```sql
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
```

## Status Monitoring

### Check Overall Sync Status
```bash
# Basic sync state
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "SELECT * FROM sync_state;"

# Formatted sync status
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    'Last Sync: ' || last_sync_time as status,
    'Total Synced: ' || total_synced as count
FROM sync_state;"
```

### Count Records by Status
```bash
# Count by processing status
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    processing_status, 
    COUNT(*) as count 
FROM synced_lifelogs 
GROUP BY processing_status;"

# Total counts
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    COUNT(*) as total_lifelogs,
    COUNT(CASE WHEN processing_status = 'processed' THEN 1 END) as successful,
    COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed,
    COUNT(CASE WHEN processing_status = 'pending' THEN 1 END) as pending
FROM synced_lifelogs;"
```

### Recent Activity
```bash
# Last 10 synced lifelogs
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    lifelog_id,
    title,
    processing_status,
    datetime(synced_at) as synced_time
FROM synced_lifelogs 
ORDER BY synced_at DESC 
LIMIT 10;"

# Today's activity
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    COUNT(*) as todays_syncs,
    COUNT(CASE WHEN processing_status = 'processed' THEN 1 END) as successful
FROM synced_lifelogs 
WHERE date(synced_at) = date('now');"
```

## Sync State Management

### Reset Sync Time (Force Resync)
```bash
# Reset to beginning of today (safe - won't create duplicates)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state 
SET last_sync_time = date('now') || 'T00:00:00+00:00';"

# Reset to specific date/time
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state 
SET last_sync_time = '2025-08-01T06:00:00+00:00';"

# Reset to 24 hours ago
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state 
SET last_sync_time = datetime('now', '-1 day') || '+00:00';"
```

### Update Sync Counters
```bash
# Recalculate total synced count
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state 
SET total_synced = (SELECT COUNT(*) FROM synced_lifelogs);"

# Reset counters to zero
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state 
SET total_synced = 0;"
```

## Lifelog Management

### View Lifelog Details
```bash
# All lifelogs with details
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    lifelog_id,
    memory_box_id,
    title,
    processing_status,
    retry_count,
    datetime(synced_at) as synced_time
FROM synced_lifelogs 
ORDER BY synced_at DESC;"

# Specific lifelog by ID
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT * FROM synced_lifelogs 
WHERE lifelog_id = 'YOUR_LIFELOG_ID_HERE';"

# Failed lifelogs
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    lifelog_id,
    title,
    last_error,
    retry_count,
    datetime(synced_at) as failed_time
FROM synced_lifelogs 
WHERE processing_status = 'failed'
ORDER BY synced_at DESC;"
```

### Remove Specific Lifelogs
```bash
# Remove a specific lifelog (will be resynced)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM synced_lifelogs 
WHERE lifelog_id = 'YOUR_LIFELOG_ID_HERE';"

# Remove failed lifelogs (for retry)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM synced_lifelogs 
WHERE processing_status = 'failed';"

# Remove lifelogs from specific date
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM synced_lifelogs 
WHERE date(start_time) = '2025-08-01';"
```

### Update Lifelog Status
```bash
# Reset failed lifelogs to pending (for retry)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE synced_lifelogs 
SET processing_status = 'pending', retry_count = 0, last_error = NULL
WHERE processing_status = 'failed';"

# Mark specific lifelog as failed
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE synced_lifelogs 
SET processing_status = 'failed', last_error = 'Manual reset'
WHERE lifelog_id = 'YOUR_LIFELOG_ID_HERE';"
```

## Error Management

### View Errors
```bash
# Recent errors
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    lifelog_id,
    error_type,
    error_message,
    datetime(occurred_at) as error_time
FROM sync_errors 
ORDER BY occurred_at DESC 
LIMIT 20;"

# Error summary
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    error_type,
    COUNT(*) as count,
    MAX(datetime(occurred_at)) as latest_occurrence
FROM sync_errors 
GROUP BY error_type 
ORDER BY count DESC;"

# Errors for specific lifelog
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT * FROM sync_errors 
WHERE lifelog_id = 'YOUR_LIFELOG_ID_HERE'
ORDER BY occurred_at DESC;"
```

### Clean Up Errors
```bash
# Delete old errors (older than 30 days)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM sync_errors 
WHERE datetime(occurred_at) < datetime('now', '-30 days');"

# Delete all errors
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM sync_errors;"

# Mark errors as resolved
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_errors 
SET resolved_at = datetime('now')
WHERE resolved_at IS NULL;"
```

## Performance Maintenance

### View Metrics
```bash
# Recent sync performance
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    datetime(sync_started_at) as sync_time,
    lifelogs_processed,
    lifelogs_successful,
    lifelogs_failed,
    ROUND(total_duration_seconds, 2) as duration_sec,
    ROUND(average_processing_time_ms, 2) as avg_time_ms
FROM sync_metrics 
ORDER BY sync_started_at DESC 
LIMIT 10;"

# Performance summary
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    COUNT(*) as total_syncs,
    SUM(lifelogs_processed) as total_processed,
    AVG(total_duration_seconds) as avg_duration,
    AVG(average_processing_time_ms) as avg_processing_time
FROM sync_metrics;"
```

### Database Optimization
```bash
# Analyze database
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "ANALYZE;"

# Vacuum database (reclaim space)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "VACUUM;"

# Check database integrity
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "PRAGMA integrity_check;"

# Database size information
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 
    name,
    COUNT(*) as row_count
FROM (
    SELECT 'sync_state' as name FROM sync_state
    UNION ALL SELECT 'synced_lifelogs' FROM synced_lifelogs
    UNION ALL SELECT 'sync_errors' FROM sync_errors
    UNION ALL SELECT 'sync_metrics' FROM sync_metrics
) 
GROUP BY name;"
```

## Backup and Recovery

### Create Backup
```bash
# Create backup with timestamp
docker-compose exec limitless-sync sh -c "
sqlite3 /app/data/limitless_sync.db '.backup /app/data/backup_$(date +%Y%m%d_%H%M%S).db'
"

# Export to SQL file
docker-compose exec limitless-sync sh -c "
sqlite3 /app/data/limitless_sync.db '.dump' > /app/data/backup_$(date +%Y%m%d_%H%M%S).sql
"
```

### Restore from Backup
```bash
# Stop the sync agent first
docker-compose stop limitless-sync

# Restore from backup
docker-compose exec limitless-sync cp /app/data/backup_YYYYMMDD_HHMMSS.db /app/data/limitless_sync.db

# Start the sync agent
docker-compose start limitless-sync
```

## Troubleshooting Scenarios

### Scenario 1: Force Complete Resync
```bash
# WARNING: This will create duplicates in Memory Box!
# Only use if you need to completely start over

# 1. Clear all tracking data
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM synced_lifelogs;
DELETE FROM sync_errors;
UPDATE sync_state SET last_sync_time = '2025-08-01T00:00:00+00:00', total_synced = 0;
"

# 2. Restart container
docker-compose restart limitless-sync
```

### Scenario 2: Resync Failed Lifelogs Only
```bash
# 1. Remove failed lifelog records
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM synced_lifelogs WHERE processing_status = 'failed';
"

# 2. Reset sync time to capture failed items
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state SET last_sync_time = datetime('now', '-1 day') || '+00:00';
"

# 3. Restart container
docker-compose restart limitless-sync
```

### Scenario 3: Sync from Specific Date (Safe)
```bash
# This won't create duplicates - existing records prevent reprocessing

# 1. Reset sync time only
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state SET last_sync_time = '2025-08-01T06:00:00+00:00';
"

# 2. Restart container
docker-compose restart limitless-sync
```

### Scenario 4: Clean Up Old Data
```bash
# Remove old data (older than 90 days)
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
DELETE FROM sync_errors WHERE datetime(occurred_at) < datetime('now', '-90 days');
DELETE FROM sync_metrics WHERE datetime(sync_started_at) < datetime('now', '-90 days');
DELETE FROM synced_lifelogs WHERE datetime(synced_at) < datetime('now', '-90 days');
"

# Update counters
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
UPDATE sync_state SET total_synced = (SELECT COUNT(*) FROM synced_lifelogs);
"

# Optimize database
docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "VACUUM;"
```

### Scenario 5: Debug Specific Lifelog
```bash
# Get all information about a specific lifelog
LIFELOG_ID="your_lifelog_id_here"

docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "
SELECT 'LIFELOG RECORD:' as info;
SELECT * FROM synced_lifelogs WHERE lifelog_id = '$LIFELOG_ID';

SELECT 'RELATED ERRORS:' as info;
SELECT * FROM sync_errors WHERE lifelog_id = '$LIFELOG_ID';
"
```

## Important Notes

### Before Making Changes
1. **Always backup** your database before making significant changes
2. **Stop the sync agent** if making structural changes: `docker-compose stop limitless-sync`
3. **Restart the container** after database changes: `docker-compose restart limitless-sync`

### Understanding Duplicate Prevention
- The sync agent uses `lifelog_id` to prevent duplicates
- Removing records from `synced_lifelogs` will cause re-syncing
- Changing only `last_sync_time` is safe - existing records prevent duplicates

### Time Formats
- All timestamps are stored in ISO 8601 format with UTC timezone
- Use format: `YYYY-MM-DDTHH:MM:SS+00:00`
- SQLite `datetime()` functions work with these formats

### Container Restart Required
After any database changes, restart the container to ensure the sync agent picks up the changes:
```bash
docker-compose restart limitless-sync
```

## Getting Help

If you encounter issues:
1. Check the container logs: `docker-compose logs -f limitless-sync`
2. Verify database integrity: `PRAGMA integrity_check;`
3. Check sync agent health: `curl http://localhost:8080/health`
4. Review recent errors in the `sync_errors` table

For more information, see the main README.md file.
