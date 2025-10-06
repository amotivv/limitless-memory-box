"""
Limitless API client with rate limiting and error handling.

Provides rate-limited, resilient client for Limitless API integration.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import httpx

from .config import Config
from .models import LifelogEntry, SyncError
from .rate_limiter import (
    AdaptiveRateLimiter, RateLimitConfig, CircuitBreaker, 
    CircuitBreakerOpenError, retry_with_backoff
)

logger = logging.getLogger(__name__)


class LimitlessAPIError(Exception):
    """Base exception for Limitless API errors."""
    pass


class LimitlessRateLimitError(LimitlessAPIError):
    """Raised when rate limit is exceeded."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class LimitlessAuthenticationError(LimitlessAPIError):
    """Raised when authentication fails."""
    pass


class LimitlessClient:
    """
    Limitless API client with rate limiting and resilience features.
    
    Features:
    - Adaptive rate limiting (180 req/min default)
    - Circuit breaker for service failures
    - Automatic retry with exponential backoff
    - Cursor-based pagination handling
    - Comprehensive error handling
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        # Initialize rate limiter
        rate_config = RateLimitConfig(
            requests_per_minute=config.rate_limit_requests_per_minute,
            burst_capacity=min(config.rate_limit_requests_per_minute, 30)  # Allow some burst
        )
        self.rate_limiter = AdaptiveRateLimiter(rate_config)
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=httpx.HTTPError
        )
        
        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=config.limitless_api_url,
            headers={
                "X-API-Key": config.limitless_api_key,
                "User-Agent": "Limitless-MemoryBox-Sync/1.0.0",
                "Accept": "application/json"
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        logger.info(f"Limitless client initialized for {config.limitless_api_url}")
    
    async def fetch_lifelogs(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: Optional[int] = None,
        include_starred_only: bool = False,
        direction: str = "asc",
        include_markdown: bool = True,
        include_headings: bool = True,
        include_contents: bool = True
    ) -> List[LifelogEntry]:
        """
        Fetch lifelogs from Limitless API with pagination.
        
        Args:
            start_date: Fetch lifelogs after this date
            end_date: Fetch lifelogs before this date
            date: Get all entries for a specific date (YYYY-MM-DD format)
            search_query: Search query for finding specific lifelogs
            limit: Maximum number of lifelogs to fetch (None for all)
            include_starred_only: Only fetch starred lifelogs
            direction: Sort direction ("asc" or "desc")
            include_markdown: Whether to include markdown content
            include_headings: Whether to include headings
            include_contents: Whether to include structured content segments (default: True)
                             Note: API automatically excludes contents when >25 results are returned
            
        Returns:
            List of LifelogEntry objects
        """
        lifelogs = []
        cursor = None
        fetched_count = 0
        batch_size = min(self.config.batch_size, 10)  # API limit is 10 per request (per official docs)
        
        logger.info(
            f"Starting lifelog fetch: start_date={start_date}, "
            f"end_date={end_date}, limit={limit}, starred_only={include_starred_only}"
        )
        
        try:
            while True:
                # Check if we've reached the limit
                if limit and fetched_count >= limit:
                    break
                
                # Adjust batch size for final request
                current_batch_size = batch_size
                if limit:
                    remaining = limit - fetched_count
                    current_batch_size = min(batch_size, remaining)
                
                # Fetch batch
                batch = await self._fetch_lifelogs_batch(
                    start_date=start_date,
                    end_date=end_date,
                    cursor=cursor,
                    limit=current_batch_size,
                    include_starred_only=include_starred_only,
                    include_contents=include_contents
                )
                
                if not batch["lifelogs"]:
                    logger.debug("No more lifelogs to fetch")
                    break
                
                # Process batch
                for lifelog_data in batch["lifelogs"]:
                    try:
                        lifelog = LifelogEntry.from_api_response(lifelog_data)
                        lifelogs.append(lifelog)
                        fetched_count += 1
                    except Exception as e:
                        logger.error(f"Failed to parse lifelog {lifelog_data.get('id', 'unknown')}: {e}")
                        continue
                
                logger.debug(f"Fetched batch of {len(batch['lifelogs'])} lifelogs, total: {fetched_count}")
                
                # Check for next page
                cursor = batch.get("next_cursor")
                if not cursor:
                    logger.debug("No more pages available")
                    break
                
                # Small delay between requests to be respectful
                await asyncio.sleep(0.1)
        
        except Exception as e:
            logger.error(f"Error fetching lifelogs: {e}")
            raise LimitlessAPIError(f"Failed to fetch lifelogs: {e}") from e
        
        logger.info(f"Successfully fetched {len(lifelogs)} lifelogs")
        return lifelogs
    
    async def _fetch_lifelogs_batch(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date: Optional[str] = None,
        search_query: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 10,
        include_starred_only: bool = False,
        direction: str = "asc",
        include_markdown: bool = True,
        include_headings: bool = True,
        include_contents: bool = True
    ) -> Dict[str, Any]:
        """
        Fetch a single batch of lifelogs.
        
        Note: The API automatically excludes contents when >25 results are returned,
        regardless of the includeContents parameter value.
        """
        
        # Build query parameters following official MCP server patterns
        params = {
            "timezone": self.config.timezone,
            "limit": limit,
            "direction": direction,
            "includeMarkdown": str(include_markdown).lower(),
            "includeHeadings": str(include_headings).lower(),
            "includeContents": str(include_contents).lower()
        }
        
        # Add search query (following official pattern)
        if search_query:
            params["search"] = search_query
        
        # Add date filter (YYYY-MM-DD format, following official pattern)
        if date:
            params["date"] = date
        
        # Add date range filters (ISO-8601 format)
        if start_date:
            # Add small buffer to catch any updates
            buffer_date = start_date - timedelta(minutes=5)
            params["start"] = buffer_date.strftime("%Y-%m-%d %H:%M:%S")
        
        if end_date:
            params["end"] = end_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Add cursor for pagination
        if cursor:
            params["cursor"] = cursor
        
        # Add starred filter (following official pattern)
        if include_starred_only:
            params["isStarred"] = str(include_starred_only).lower()
        
        # Make API request with rate limiting and circuit breaker
        async def make_request():
            await self.rate_limiter.acquire()
            
            response = await self.client.get("/v1/lifelogs", params=params)
            await self._handle_response(response)
            return response.json()
        
        try:
            data = await self.circuit_breaker.call(make_request)
            await self.rate_limiter.record_success()
            
            # Extract lifelogs and pagination info
            lifelogs = data.get("data", {}).get("lifelogs", [])
            next_cursor = data.get("meta", {}).get("lifelogs", {}).get("nextCursor")
            
            return {
                "lifelogs": lifelogs,
                "next_cursor": next_cursor
            }
            
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker is open, Limitless API unavailable")
            raise LimitlessAPIError("Limitless API is currently unavailable")
        
        except Exception as e:
            await self.rate_limiter.record_error()
            raise
    
    async def get_lifelog_by_id(self, lifelog_id: str) -> Optional[LifelogEntry]:
        """
        Get a specific lifelog by ID.
        
        Args:
            lifelog_id: The lifelog ID to fetch
            
        Returns:
            LifelogEntry or None if not found
        """
        logger.debug(f"Fetching lifelog by ID: {lifelog_id}")
        
        async def make_request():
            await self.rate_limiter.acquire()
            
            response = await self.client.get(
                f"/v1/lifelogs/{lifelog_id}",
                params={
                    "timezone": self.config.timezone,
                    "includeContents": "true",
                    "includeMarkdown": "true",
                    "includeHeadings": "true"
                }
            )
            await self._handle_response(response)
            return response.json()
        
        try:
            data = await self.circuit_breaker.call(make_request)
            await self.rate_limiter.record_success()
            
            lifelog_data = data.get("data", {}).get("lifelog")
            if lifelog_data:
                return LifelogEntry.from_api_response(lifelog_data)
            
            return None
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Lifelog {lifelog_id} not found")
                return None
            raise
        
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker is open, Limitless API unavailable")
            raise LimitlessAPIError("Limitless API is currently unavailable")
        
        except Exception as e:
            await self.rate_limiter.record_error()
            logger.error(f"Error fetching lifelog {lifelog_id}: {e}")
            raise LimitlessAPIError(f"Failed to fetch lifelog {lifelog_id}: {e}") from e
    
    async def _handle_response(self, response: httpx.Response) -> None:
        """Handle API response and errors."""
        
        # Handle rate limiting
        if response.status_code == 429:
            retry_after = None
            if "retry-after" in response.headers:
                try:
                    retry_after = int(response.headers["retry-after"])
                except ValueError:
                    pass
            
            await self.rate_limiter.record_rate_limit(retry_after)
            raise LimitlessRateLimitError(
                "Rate limit exceeded", 
                retry_after=retry_after
            )
        
        # Handle authentication errors
        if response.status_code == 401:
            raise LimitlessAuthenticationError("Invalid API key or authentication failed")
        
        # Handle other HTTP errors
        if response.status_code >= 400:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get("error", error_detail)
            except Exception:
                error_detail = response.text or f"HTTP {response.status_code}"
            
            logger.error(f"Limitless API error {response.status_code}: {error_detail}")
            response.raise_for_status()
    
    async def test_connection(self) -> bool:
        """
        Test connection to Limitless API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Testing Limitless API connection...")
            
            # Try to fetch a small batch of lifelogs
            await self._fetch_lifelogs_batch(limit=1)
            
            logger.info("Limitless API connection test successful")
            return True
            
        except LimitlessAuthenticationError:
            logger.error("Limitless API authentication failed - check API key")
            return False
        
        except Exception as e:
            logger.error(f"Limitless API connection test failed: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        rate_stats = await self.rate_limiter.get_stats()
        circuit_stats = await self.circuit_breaker.get_stats()
        
        return {
            "rate_limiter": rate_stats,
            "circuit_breaker": circuit_stats,
            "api_url": self.config.limitless_api_url
        }
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("Limitless client closed")


async def create_limitless_client(config: Config) -> LimitlessClient:
    """
    Factory function to create and test Limitless client.
    
    Args:
        config: Application configuration
        
    Returns:
        Configured LimitlessClient
        
    Raises:
        LimitlessAPIError: If client creation or connection test fails
    """
    client = LimitlessClient(config)
    
    # Test connection
    if not await client.test_connection():
        await client.close()
        raise LimitlessAPIError("Failed to connect to Limitless API")
    
    return client
