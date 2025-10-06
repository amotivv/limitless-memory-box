# Testing API Compliance Updates

This document provides testing instructions for the Limitless API compliance updates made on October 6, 2025.

## Changes Summary

### 1. Fixed Batch Size Limit
- **Changed from:** 25 lifelogs per request
- **Changed to:** 10 lifelogs per request
- **Reason:** Official API documentation specifies max limit of 10, not 25

### 2. Added `includeContents` Parameter
- **Added:** Explicit `include_contents=True` parameter to all lifelog fetch operations
- **Reason:** Ensures structured content segments are included (API default is false)
- **Impact:** Makes content retrieval explicit and future-proof

### 3. Updated API Parameters
- Added `includeHeadings: "true"` to single lifelog fetch for consistency
- Updated documentation to reflect correct API limits

## Testing Strategy

### Pre-Testing Checklist
- [ ] Ensure `.env` file has valid API keys
- [ ] Backup your database: `cp data/limitless_sync.db data/limitless_sync.db.backup`
- [ ] Check current sync status

### Test 1: Local Development Test
```bash
# Stop any running containers
docker-compose down

# Test locally with Python
python limitless_sync.py

# Expected behavior:
# - Should initialize successfully
# - Should fetch lifelogs in batches of 10 (check logs)
# - Should include structured contents in responses
# - Should sync successfully to Memory Box
```

### Test 2: Docker Build Test
```bash
# Build Docker image
docker build -t limitless-sync:test .

# Should build without errors
```

### Test 3: Integration Test with Docker Compose
```bash
# Start with docker-compose
docker-compose up -d

# Watch logs in real-time
docker-compose logs -f limitless-sync

# Verify:
# 1. Check logs for "API limit is 10 per request" comment validation
# 2. Verify batch fetching works correctly
# 3. Confirm structured contents are present in logs
# 4. Check successful sync to Memory Box
```

### Test 4: Health Check Verification
```bash
# Check health endpoint
curl http://localhost:8080/health

# Expected response:
# {
#   "healthy": true,
#   "checks": {
#     "database": true,
#     "limitless_api": true,
#     "memorybox_api": true
#   },
#   "message": "All systems operational"
# }
```

### Test 5: API Response Validation
```bash
# Enable debug logging to see full API responses
# Add to .env:
LOG_LEVEL=DEBUG

# Restart and check logs for:
# - includeContents parameter in API requests
# - Structured content in responses (contents array)
# - Batch size never exceeding 10 items
```

## Monitoring Points

### Log Messages to Look For
1. **Successful Initialization:**
   ```
   Limitless client initialized for https://api.limitless.ai
   ```

2. **Batch Fetching:**
   ```
   Fetched batch of X lifelogs, total: Y
   ```
   - X should never exceed 10

3. **API Parameters:**
   ```
   # In DEBUG mode, should see requests with:
   includeContents=true
   includeMarkdown=true
   includeHeadings=true
   ```

4. **Sync Success:**
   ```
   Successfully synced lifelog {id} to memory {memory_id}
   ```

### Key Metrics to Monitor
- **Batch Size:** Should never exceed 10 lifelogs per request
- **Content Availability:** All lifelogs should have `contents` array populated
- **Success Rate:** Should maintain same success rate as before
- **API Errors:** Watch for any 400 errors (would indicate parameter issues)

## Expected Behavior Changes

### What SHOULD Change:
1. ✅ Smaller batches (max 10 instead of 25)
2. ✅ More pagination requests for large datasets
3. ✅ Explicit `includeContents=true` in all API calls

### What should NOT Change:
1. ❌ Overall sync success rate
2. ❌ Content quality or completeness
3. ❌ Memory Box creation behavior
4. ❌ Application functionality

## Troubleshooting

### If batch size errors occur:
```python
# Check logs for:
"API limit is 10 per request"
# This indicates the limit is being respected
```

### If contents are missing:
```python
# Verify in logs that API requests include:
"includeContents": "true"
```

### If sync fails:
```bash
# Check database state
sqlite3 data/limitless_sync.db "SELECT * FROM sync_errors ORDER BY occurred_at DESC LIMIT 5;"

# Check last sync time
sqlite3 data/limitless_sync.db "SELECT * FROM sync_state ORDER BY updated_at DESC LIMIT 1;"
```

## Rollback Instructions

If issues occur and you need to rollback:

```bash
# Stop the service
docker-compose down

# Switch back to main branch
git checkout main

# Restore database backup if needed
cp data/limitless_sync.db.backup data/limitless_sync.db

# Rebuild and restart
docker-compose up -d --build
```

## Success Criteria

All tests pass if:
- ✅ No API errors (400, 429, etc.)
- ✅ Batch sizes never exceed 10
- ✅ Contents array is populated in lifelog objects
- ✅ Sync success rate matches previous performance
- ✅ Memory Box memories are created successfully
- ✅ Health checks pass

## Performance Notes

- **Slightly slower:** More pagination requests for large syncs (expected)
- **More API calls:** Breaking 25-item batches into 10-item batches
- **Same rate limits:** Still respects 180 requests/minute
- **Better compliance:** Following official API limits

## Post-Testing

After successful testing:
1. Monitor for 24 hours in production
2. Check sync metrics in database
3. Verify no increase in error rates
4. Confirm Memory Box integration stable

## Questions or Issues?

If you encounter any issues during testing:
1. Check logs with `docker-compose logs -f limitless-sync`
2. Review database errors: `sqlite3 data/limitless_sync.db "SELECT * FROM sync_errors;"`
3. Verify API key is valid and not rate limited
4. Check Limitless API status at https://www.limitless.ai/developers
