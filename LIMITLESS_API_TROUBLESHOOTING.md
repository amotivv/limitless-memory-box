# Limitless API Troubleshooting Guide

This guide provides curl commands for directly querying the Limitless API to troubleshoot sync issues and verify data availability.

## Table of Contents
- [Setup and Authentication](#setup-and-authentication)
- [Basic API Testing](#basic-api-testing)
- [Lifelog Queries](#lifelog-queries)
- [Date Range Queries](#date-range-queries)
- [Content Analysis](#content-analysis)
- [Rate Limit Testing](#rate-limit-testing)
- [Troubleshooting Scenarios](#troubleshooting-scenarios)
- [Response Analysis](#response-analysis)

## Setup and Authentication

### Environment Variables
First, set up your API credentials:
```bash
# Set your Limitless API key
export LIMITLESS_API_KEY="your_limitless_api_key_here"
export LIMITLESS_API_URL="https://api.limitless.ai"

# Verify they're set
echo "API Key: ${LIMITLESS_API_KEY:0:10}..."
echo "API URL: $LIMITLESS_API_URL"
```

### Basic Headers
All requests require the API key in the header:
```bash
# Standard headers for all requests
HEADERS="-H 'X-API-Key: $LIMITLESS_API_KEY' -H 'Accept: application/json' -H 'Content-Type: application/json'"
```

## Basic API Testing

### Test API Connection
```bash
# Simple connection test
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1" | jq '.'

# Check if API is responding
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1"
```

### Verify API Key
```bash
# Test with invalid key (should return 401)
curl -s -w "%{http_code}" \
  -H "X-API-Key: invalid_key" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1"

# Test with your key (should return 200)
curl -s -w "%{http_code}" \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1"
```

## Lifelog Queries

### Get Recent Lifelogs
```bash
# Get last 10 lifelogs
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=10&direction=desc" | jq '.'

# Get lifelogs with content included
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=5&includeContents=true" | jq '.'
```

### Get Specific Lifelog
```bash
# Get specific lifelog by ID
LIFELOG_ID="your_lifelog_id_here"
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs/$LIFELOG_ID" | jq '.'

# Get lifelog with full content
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs/$LIFELOG_ID?includeContents=true" | jq '.'
```

### Count Total Lifelogs
```bash
# Get total count (using large limit to see total)
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1000" | jq '.meta.lifelogs.total // "total not provided"'

# Alternative: Count by fetching all with minimal data
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1000&includeContents=false" | jq '.data.lifelogs | length'
```

## Date Range Queries

### Today's Lifelogs
```bash
# Get today's lifelogs (adjust timezone as needed)
TODAY=$(date +%Y-%m-%d)
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=${TODAY}%2000:00:00&timezone=America/New_York" | jq '.'

# Count today's lifelogs
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=${TODAY}%2000:00:00&timezone=America/New_York" | jq '.data.lifelogs | length'
```

### Specific Date Range
```bash
# Get lifelogs from specific date range
START_DATE="2025-08-01 06:00:00"
END_DATE="2025-08-01 18:00:00"
TIMEZONE="America/New_York"

curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=${START_DATE// /%20}&end=${END_DATE// /%20}&timezone=$TIMEZONE" | jq '.'
```

### Last N Hours
```bash
# Get lifelogs from last 6 hours
HOURS_AGO=$(date -d '6 hours ago' '+%Y-%m-%d %H:%M:%S')
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=${HOURS_AGO// /%20}&timezone=America/New_York" | jq '.'

# macOS version (using -v instead of -d)
HOURS_AGO=$(date -v-6H '+%Y-%m-%d %H:%M:%S')
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=${HOURS_AGO// /%20}&timezone=America/New_York" | jq '.'
```

## Content Analysis

### Extract Lifelog Titles
```bash
# Get just titles and IDs
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=20" | jq '.data.lifelogs[] | {id, title, startTime}'

# Search for specific keywords in titles
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=50" | jq '.data.lifelogs[] | select(.title | test("meeting|call"; "i")) | {id, title}'
```

### Analyze Content Structure
```bash
# Get lifelogs with content and analyze structure
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=5&includeContents=true" | jq '.data.lifelogs[] | {
    id,
    title,
    contentCount: (.contents | length),
    hasMarkdown: (.markdown != null and .markdown != ""),
    speakers: [.contents[]?.speakerName] | unique | map(select(. != null))
  }'
```

### Find Starred Lifelogs
```bash
# Get starred lifelogs only
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=50" | jq '.data.lifelogs[] | select(.isStarred == true) | {id, title, startTime}'

# Count starred vs unstarred
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=100" | jq '{
    total: (.data.lifelogs | length),
    starred: (.data.lifelogs | map(select(.isStarred == true)) | length),
    unstarred: (.data.lifelogs | map(select(.isStarred != true)) | length)
  }'
```

## Rate Limit Testing

### Check Rate Limit Headers
```bash
# Make request and show rate limit headers
curl -s -D headers.txt \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1" > /dev/null

# Display rate limit info
grep -i "rate\|limit\|remaining" headers.txt
rm headers.txt
```

### Test Rate Limiting
```bash
# Make multiple rapid requests to test rate limiting
echo "Testing rate limits..."
for i in {1..10}; do
  echo -n "Request $i: "
  curl -s -w "%{http_code} - %{time_total}s\n" \
    -H "X-API-Key: $LIMITLESS_API_KEY" \
    "$LIMITLESS_API_URL/v1/lifelogs?limit=1" > /dev/null
  sleep 0.1
done
```

## Troubleshooting Scenarios

### Scenario 1: Verify Sync Agent's Last Fetch
```bash
# Check what the sync agent should have fetched
# (Use the same parameters as your sync agent)
LAST_SYNC="2025-08-01T10:00:00+00:00"
TIMEZONE="America/New_York"

echo "Checking lifelogs since: $LAST_SYNC"
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=${LAST_SYNC}&timezone=$TIMEZONE&direction=asc&includeContents=true" | jq '{
    total: (.data.lifelogs | length),
    lifelogs: .data.lifelogs[] | {id, title, startTime, endTime, isStarred}
  }'
```

### Scenario 2: Compare API Data with Database
```bash
# Get lifelog IDs from API
echo "=== API Lifelogs ==="
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?start=2025-08-01T10:00:00+00:00&timezone=America/New_York" | jq -r '.data.lifelogs[].id' | sort

echo -e "\n=== Database Lifelogs ==="
# Compare with database (run this separately)
# docker-compose exec limitless-sync sqlite3 /app/data/limitless_sync.db "SELECT lifelog_id FROM synced_lifelogs ORDER BY lifelog_id;"
```

### Scenario 3: Debug Missing Lifelog
```bash
# Check if specific lifelog exists in API
MISSING_ID="your_missing_lifelog_id"
echo "Checking for lifelog: $MISSING_ID"

# Direct lookup
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs/$MISSING_ID" | jq '.'

# Search in recent lifelogs
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=100" | jq --arg id "$MISSING_ID" '.data.lifelogs[] | select(.id == $id)'
```

### Scenario 4: Verify Content Quality
```bash
# Check for lifelogs with missing or empty content
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=20&includeContents=true" | jq '.data.lifelogs[] | {
    id,
    title,
    hasMarkdown: (.markdown != null and .markdown != ""),
    hasContents: (.contents != null and (.contents | length) > 0),
    contentTypes: [.contents[]?.type] | unique
  }'
```

### Scenario 5: Check API Pagination
```bash
# Test pagination to ensure we're not missing data
echo "=== Page 1 ==="
RESPONSE=$(curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=5&direction=desc")

echo "$RESPONSE" | jq '.data.lifelogs[] | {id, title}'

# Get next cursor
NEXT_CURSOR=$(echo "$RESPONSE" | jq -r '.meta.lifelogs.nextCursor // empty')

if [ ! -z "$NEXT_CURSOR" ]; then
  echo -e "\n=== Page 2 (cursor: $NEXT_CURSOR) ==="
  curl -s \
    -H "X-API-Key: $LIMITLESS_API_KEY" \
    -H "Accept: application/json" \
    "$LIMITLESS_API_URL/v1/lifelogs?limit=5&cursor=$NEXT_CURSOR" | jq '.data.lifelogs[] | {id, title}'
fi
```

## Response Analysis

### Parse Common Response Fields
```bash
# Extract key metadata from response
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=10" | jq '{
    responseTime: now,
    totalLifelogs: (.data.lifelogs | length),
    hasNextPage: (.meta.lifelogs.nextCursor != null),
    nextCursor: .meta.lifelogs.nextCursor,
    dateRange: {
      earliest: (.data.lifelogs | map(.startTime) | min),
      latest: (.data.lifelogs | map(.startTime) | max)
    }
  }'
```

### Validate Response Structure
```bash
# Check if response has expected structure
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?limit=1" | jq '{
    hasData: (.data != null),
    hasLifelogs: (.data.lifelogs != null),
    hasMeta: (.meta != null),
    structure: {
      dataKeys: (.data | keys),
      metaKeys: (.meta | keys)
    }
  }'
```

### Error Response Analysis
```bash
# Test error responses
echo "=== Testing Invalid Endpoint ==="
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/invalid-endpoint" | jq '.'

echo -e "\n=== Testing Invalid Parameters ==="
curl -s \
  -H "X-API-Key: $LIMITLESS_API_KEY" \
  -H "Accept: application/json" \
  "$LIMITLESS_API_URL/v1/lifelogs?invalid_param=test" | jq '.'
```

## Useful One-Liners

### Quick Status Check
```bash
# Quick API health and recent activity check
curl -s -H "X-API-Key: $LIMITLESS_API_KEY" "$LIMITLESS_API_URL/v1/lifelogs?limit=5" | jq '{status: "ok", count: (.data.lifelogs|length), latest: .data.lifelogs[0].startTime}'
```

### Find Lifelogs by Date Pattern
```bash
# Find all lifelogs from today
TODAY=$(date +%Y-%m-%d)
curl -s -H "X-API-Key: $LIMITLESS_API_KEY" "$LIMITLESS_API_URL/v1/lifelogs?limit=100" | jq --arg today "$TODAY" '.data.lifelogs[] | select(.startTime | startswith($today)) | {id, title, startTime}'
```

### Export Lifelog Metadata
```bash
# Export basic metadata to CSV format
echo "id,title,startTime,endTime,isStarred"
curl -s -H "X-API-Key: $LIMITLESS_API_KEY" "$LIMITLESS_API_URL/v1/lifelogs?limit=50" | jq -r '.data.lifelogs[] | [.id, .title, .startTime, .endTime, .isStarred] | @csv'
```

## Environment Setup Script

Create a script to set up your environment:

```bash
#!/bin/bash
# save as setup_limitless_api.sh

# Load API key from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set API URL
export LIMITLESS_API_URL="https://api.limitless.ai"

# Test connection
echo "Testing Limitless API connection..."
if curl -s -f -H "X-API-Key: $LIMITLESS_API_KEY" "$LIMITLESS_API_URL/v1/lifelogs?limit=1" > /dev/null; then
    echo "✅ API connection successful"
    echo "API Key: ${LIMITLESS_API_KEY:0:10}..."
    echo "API URL: $LIMITLESS_API_URL"
else
    echo "❌ API connection failed"
    echo "Check your LIMITLESS_API_KEY in .env file"
fi
```

## Tips and Best Practices

### Rate Limiting
- The Limitless API has a limit of 180 requests per minute
- Add delays between requests: `sleep 0.5`
- Monitor rate limit headers in responses

### Error Handling
- Always check HTTP status codes: `curl -w "%{http_code}"`
- Use `-f` flag to fail on HTTP errors: `curl -f`
- Parse error responses: `jq '.error // .message // .'`

### Data Validation
- Verify required fields exist: `jq 'has("data") and has("meta")'`
- Check for null values: `jq '.data.lifelogs[] | select(.title != null)'`
- Validate date formats: `jq '.data.lifelogs[].startTime | strptime("%Y-%m-%dT%H:%M:%S")'`

### Performance
- Use `includeContents=false` when you don't need full content
- Limit results appropriately: `limit=10` for testing
- Use pagination for large datasets

For more information about the Limitless API, refer to the official documentation or contact Limitless support.
