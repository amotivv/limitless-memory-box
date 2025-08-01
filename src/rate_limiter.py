"""
Rate limiting implementation for API clients.

Provides token bucket algorithm for respecting API rate limits.
"""

import asyncio
import time
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_minute: int = 180
    burst_capacity: Optional[int] = None  # If None, uses requests_per_minute
    
    def __post_init__(self):
        if self.burst_capacity is None:
            self.burst_capacity = self.requests_per_minute


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter implementation.
    
    Allows burst requests up to capacity, then refills at a steady rate.
    """
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.capacity = config.burst_capacity
        self.tokens = float(self.capacity)
        self.refill_rate = config.requests_per_minute / 60.0  # tokens per second
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        
        logger.info(
            f"Rate limiter initialized: {config.requests_per_minute} req/min, "
            f"burst capacity: {self.capacity}"
        )
    
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens from the bucket.
        
        Blocks until sufficient tokens are available.
        """
        async with self.lock:
            await self._refill_tokens()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                logger.debug(f"Acquired {tokens} tokens, {self.tokens:.2f} remaining")
                return
            
            # Calculate wait time
            needed_tokens = tokens - self.tokens
            wait_time = needed_tokens / self.refill_rate
            
            logger.debug(
                f"Rate limit reached, waiting {wait_time:.2f}s for {needed_tokens} tokens"
            )
            
            await asyncio.sleep(wait_time)
            
            # Refill after waiting and try again
            await self._refill_tokens()
            self.tokens -= tokens
            
            logger.debug(f"Acquired {tokens} tokens after wait, {self.tokens:.2f} remaining")
    
    async def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        if elapsed > 0:
            new_tokens = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now
    
    async def get_available_tokens(self) -> float:
        """Get current number of available tokens."""
        async with self.lock:
            await self._refill_tokens()
            return self.tokens
    
    async def get_wait_time(self, tokens: int = 1) -> float:
        """Get estimated wait time for acquiring tokens."""
        async with self.lock:
            await self._refill_tokens()
            
            if self.tokens >= tokens:
                return 0.0
            
            needed_tokens = tokens - self.tokens
            return needed_tokens / self.refill_rate


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts based on API responses.
    
    Reduces rate when receiving 429 responses and gradually increases back.
    """
    
    def __init__(self, config: RateLimitConfig):
        self.base_config = config
        self.current_rate = config.requests_per_minute
        self.bucket = TokenBucketRateLimiter(config)
        self.consecutive_successes = 0
        self.last_rate_limit = None
        self.lock = asyncio.Lock()
        
        logger.info(f"Adaptive rate limiter initialized at {self.current_rate} req/min")
    
    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens with adaptive rate limiting."""
        await self.bucket.acquire(tokens)
    
    async def record_success(self) -> None:
        """Record a successful API call."""
        async with self.lock:
            self.consecutive_successes += 1
            
            # Gradually increase rate after sustained success
            if (self.consecutive_successes >= 10 and 
                self.current_rate < self.base_config.requests_per_minute):
                
                old_rate = self.current_rate
                self.current_rate = min(
                    self.base_config.requests_per_minute,
                    self.current_rate * 1.1
                )
                
                if self.current_rate != old_rate:
                    await self._update_rate_limiter()
                    logger.info(f"Rate limit increased to {self.current_rate:.1f} req/min")
                    self.consecutive_successes = 0
    
    async def record_rate_limit(self, retry_after: Optional[int] = None) -> None:
        """Record a rate limit response (429)."""
        async with self.lock:
            self.consecutive_successes = 0
            self.last_rate_limit = time.time()
            
            # Reduce rate more aggressively
            old_rate = self.current_rate
            self.current_rate = max(
                self.base_config.requests_per_minute * 0.1,  # Minimum 10% of base rate
                self.current_rate * 0.5  # Halve the current rate
            )
            
            await self._update_rate_limiter()
            logger.warning(
                f"Rate limit hit, reduced from {old_rate:.1f} to {self.current_rate:.1f} req/min"
            )
            
            # If retry-after header provided, wait that long
            if retry_after:
                logger.info(f"Waiting {retry_after}s as requested by API")
                await asyncio.sleep(retry_after)
    
    async def record_error(self) -> None:
        """Record a non-rate-limit error."""
        async with self.lock:
            # Reset success counter but don't change rate
            self.consecutive_successes = 0
    
    async def _update_rate_limiter(self) -> None:
        """Update the underlying token bucket with new rate."""
        new_config = RateLimitConfig(
            requests_per_minute=int(self.current_rate),
            burst_capacity=self.base_config.burst_capacity
        )
        self.bucket = TokenBucketRateLimiter(new_config)
    
    async def get_current_rate(self) -> float:
        """Get current rate limit."""
        return self.current_rate
    
    async def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        available_tokens = await self.bucket.get_available_tokens()
        
        return {
            "current_rate_per_minute": self.current_rate,
            "base_rate_per_minute": self.base_config.requests_per_minute,
            "available_tokens": available_tokens,
            "consecutive_successes": self.consecutive_successes,
            "last_rate_limit": self.last_rate_limit
        }


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.
    
    Fails fast when service is consistently unavailable.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.lock = asyncio.Lock()
        
        logger.info(
            f"Circuit breaker initialized: threshold={failure_threshold}, "
            f"timeout={recovery_timeout}s"
        )
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        async with self.lock:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
            
        except self.expected_exception as e:
            await self._record_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        
        return time.time() - self.last_failure_time >= self.recovery_timeout
    
    async def _record_success(self) -> None:
        """Record successful operation."""
        async with self.lock:
            self.failure_count = 0
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                logger.info("Circuit breaker reset to CLOSED state")
    
    async def _record_failure(self) -> None:
        """Record failed operation."""
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(
                    f"Circuit breaker opened after {self.failure_count} failures"
                )
    
    async def get_state(self) -> str:
        """Get current circuit breaker state."""
        return self.state
    
    async def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.recovery_timeout
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


async def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
):
    """
    Retry function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delays
    """
    import random
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(f"All {max_retries + 1} attempts failed, giving up")
                raise
            
            # Calculate delay
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            
            # Add jitter
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)
            
            logger.warning(
                f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s"
            )
            
            await asyncio.sleep(delay)
    
    # This should never be reached, but just in case
    raise last_exception
