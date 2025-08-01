"""
Memory Box API client following MCP server patterns.

Provides Memory Box API integration with status polling and bucket management.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import httpx

from .config import Config
from .models import LifelogEntry, MemoryBoxReferenceData, ProcessingStatus
from .rate_limiter import CircuitBreaker, CircuitBreakerOpenError, retry_with_backoff

logger = logging.getLogger(__name__)


class MemoryBoxAPIError(Exception):
    """Base exception for Memory Box API errors."""
    pass


class MemoryBoxAuthenticationError(MemoryBoxAPIError):
    """Raised when authentication fails."""
    pass


class MemoryBoxProcessingError(MemoryBoxAPIError):
    """Raised when memory processing fails."""
    pass


class MemoryBoxClient:
    """
    Memory Box API client following MCP server patterns.
    
    Features:
    - Bearer token authentication
    - Status polling for processing completion
    - Bucket management
    - Rich reference data structure
    - Circuit breaker for resilience
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=httpx.HTTPError
        )
        
        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=config.memorybox_api_url,
            headers={
                "Authorization": f"Bearer {config.memorybox_api_key}",
                "User-Agent": "Limitless-MemoryBox-Sync/1.0.0",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        logger.info(f"Memory Box client initialized for {config.memorybox_api_url}")
    
    async def create_memory(
        self, 
        lifelog_entry: LifelogEntry,
        formatted_content: str,
        reference_data: MemoryBoxReferenceData
    ) -> Optional[int]:
        """
        Create a memory in Memory Box and wait for processing completion.
        
        Args:
            lifelog_entry: The original lifelog entry
            formatted_content: Formatted content for Memory Box
            reference_data: Rich metadata structure
            
        Returns:
            Memory ID if successful, None if failed
        """
        logger.debug(f"Creating memory for lifelog {lifelog_entry.id}")
        
        try:
            # Create the memory
            memory_id = await self._create_memory_request(
                formatted_content, 
                reference_data
            )
            
            if not memory_id:
                logger.error(f"Failed to create memory for lifelog {lifelog_entry.id}")
                return None
            
            logger.info(f"Created memory {memory_id} for lifelog {lifelog_entry.id}")
            
            # Poll for processing completion
            if await self._poll_processing_status(memory_id):
                logger.info(f"Memory {memory_id} processed successfully")
                return memory_id
            else:
                logger.warning(f"Memory {memory_id} processing failed or timed out")
                return None
                
        except Exception as e:
            logger.error(f"Error creating memory for lifelog {lifelog_entry.id}: {e}")
            return None
    
    async def _create_memory_request(
        self, 
        content: str, 
        reference_data: MemoryBoxReferenceData
    ) -> Optional[int]:
        """Make the actual memory creation request."""
        
        payload = {
            "raw_content": content,
            "bucketId": self.config.memorybox_bucket,
            "source_type": "application_plugin",
            "reference_data": reference_data.to_memory_box_format()
        }
        
        async def make_request():
            response = await self.client.post("/api/v2/memory", json=payload)
            await self._handle_response(response)
            return response.json()
        
        try:
            data = await self.circuit_breaker.call(make_request)
            return data.get("id")
            
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker is open, Memory Box API unavailable")
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
        
        except Exception as e:
            logger.error(f"Failed to create memory: {e}")
            raise MemoryBoxAPIError(f"Failed to create memory: {e}") from e
    
    async def _poll_processing_status(self, memory_id: int) -> bool:
        """
        Poll Memory Box for processing completion.
        
        Args:
            memory_id: The memory ID to check
            
        Returns:
            True if processed successfully, False if failed or timed out
        """
        logger.debug(f"Polling processing status for memory {memory_id}")
        
        for attempt in range(self.config.max_poll_attempts):
            try:
                status_data = await self._get_memory_status(memory_id)
                status = status_data.get("processing_status")
                
                logger.debug(f"Memory {memory_id} status: {status} (attempt {attempt + 1})")
                
                if status == "processed":
                    return True
                elif status == "failed":
                    logger.error(f"Memory {memory_id} processing failed")
                    return False
                elif status in ["pending", "processing"]:
                    # Continue polling
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue
                else:
                    logger.warning(f"Unknown processing status for memory {memory_id}: {status}")
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue
                    
            except Exception as e:
                logger.error(f"Error polling status for memory {memory_id}: {e}")
                # Continue trying unless it's the last attempt
                if attempt < self.config.max_poll_attempts - 1:
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue
                else:
                    return False
        
        logger.warning(f"Polling timed out for memory {memory_id} after {self.config.max_poll_attempts} attempts")
        return False
    
    async def _get_memory_status(self, memory_id: int) -> Dict[str, Any]:
        """Get memory processing status."""
        
        async def make_request():
            response = await self.client.get(f"/api/v2/memory/{memory_id}/status")
            await self._handle_response(response)
            return response.json()
        
        try:
            return await self.circuit_breaker.call(make_request)
        except CircuitBreakerOpenError:
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
    
    async def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific memory by ID."""
        
        async def make_request():
            response = await self.client.get(f"/api/v2/memory/{memory_id}")
            await self._handle_response(response)
            return response.json()
        
        try:
            return await self.circuit_breaker.call(make_request)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except CircuitBreakerOpenError:
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
    
    async def search_memories(
        self, 
        query: str, 
        bucket_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search memories using semantic search."""
        
        params = {
            "query": query,
            "limit": limit
        }
        
        if bucket_id:
            params["bucketId"] = bucket_id
        
        async def make_request():
            response = await self.client.get("/api/v2/memory", params=params)
            await self._handle_response(response)
            return response.json()
        
        try:
            data = await self.circuit_breaker.call(make_request)
            
            # Handle different response formats
            if "results" in data:
                return data["results"]
            elif "items" in data:
                return data["items"]
            else:
                return []
                
        except CircuitBreakerOpenError:
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
    
    async def ensure_bucket_exists(self, bucket_name: Optional[str] = None) -> bool:
        """
        Ensure the specified bucket exists, create if needed.
        
        Args:
            bucket_name: Bucket name (uses config default if None)
            
        Returns:
            True if bucket exists or was created successfully
        """
        if bucket_name is None:
            bucket_name = self.config.memorybox_bucket
        
        logger.debug(f"Ensuring bucket exists: {bucket_name}")
        
        try:
            # Check if bucket exists
            buckets = await self._get_buckets()
            bucket_names = [b.get("name") for b in buckets]
            
            if bucket_name in bucket_names:
                logger.debug(f"Bucket {bucket_name} already exists")
                return True
            
            # Create bucket
            logger.info(f"Creating bucket: {bucket_name}")
            await self._create_bucket(bucket_name)
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring bucket {bucket_name} exists: {e}")
            return False
    
    async def _get_buckets(self) -> List[Dict[str, Any]]:
        """Get list of all buckets."""
        
        async def make_request():
            response = await self.client.get("/api/v2/buckets")
            await self._handle_response(response)
            return response.json()
        
        try:
            data = await self.circuit_breaker.call(make_request)
            return data.get("items", [])
        except CircuitBreakerOpenError:
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
    
    async def _create_bucket(self, bucket_name: str) -> Dict[str, Any]:
        """Create a new bucket."""
        
        async def make_request():
            response = await self.client.post(
                "/api/v2/buckets",
                params={"bucket_name": bucket_name}
            )
            await self._handle_response(response)
            return response.json()
        
        try:
            return await self.circuit_breaker.call(make_request)
        except CircuitBreakerOpenError:
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get user usage statistics."""
        
        async def make_request():
            response = await self.client.get("/api/v2/usage")
            await self._handle_response(response)
            return response.json()
        
        try:
            return await self.circuit_breaker.call(make_request)
        except CircuitBreakerOpenError:
            raise MemoryBoxAPIError("Memory Box API is currently unavailable")
    
    async def _handle_response(self, response: httpx.Response) -> None:
        """Handle API response and errors."""
        
        # Handle authentication errors
        if response.status_code == 401:
            raise MemoryBoxAuthenticationError("Invalid API key or authentication failed")
        
        # Handle other HTTP errors
        if response.status_code >= 400:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", error_data.get("error", error_detail))
            except Exception:
                error_detail = response.text or f"HTTP {response.status_code}"
            
            logger.error(f"Memory Box API error {response.status_code}: {error_detail}")
            response.raise_for_status()
    
    async def test_connection(self) -> bool:
        """
        Test connection to Memory Box API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info("Testing Memory Box API connection...")
            
            # Try to get buckets (simple operation)
            await self._get_buckets()
            
            logger.info("Memory Box API connection test successful")
            return True
            
        except MemoryBoxAuthenticationError:
            logger.error("Memory Box API authentication failed - check API key")
            return False
        
        except Exception as e:
            logger.error(f"Memory Box API connection test failed: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        circuit_stats = await self.circuit_breaker.get_stats()
        
        try:
            usage_stats = await self.get_usage_stats()
        except Exception as e:
            logger.warning(f"Could not fetch usage stats: {e}")
            usage_stats = {"error": str(e)}
        
        return {
            "circuit_breaker": circuit_stats,
            "api_url": self.config.memorybox_api_url,
            "bucket": self.config.memorybox_bucket,
            "usage_stats": usage_stats
        }
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("Memory Box client closed")


async def create_memorybox_client(config: Config) -> MemoryBoxClient:
    """
    Factory function to create and test Memory Box client.
    
    Args:
        config: Application configuration
        
    Returns:
        Configured MemoryBoxClient
        
    Raises:
        MemoryBoxAPIError: If client creation or connection test fails
    """
    client = MemoryBoxClient(config)
    
    # Test connection
    if not await client.test_connection():
        await client.close()
        raise MemoryBoxAPIError("Failed to connect to Memory Box API")
    
    # Ensure bucket exists
    if not await client.ensure_bucket_exists():
        await client.close()
        raise MemoryBoxAPIError(f"Failed to ensure bucket '{config.memorybox_bucket}' exists")
    
    return client
