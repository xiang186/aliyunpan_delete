"""
API rate limiter with interval control and exponential backoff retry.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for the rate limiter."""

    interval_ms: int = 200          # Minimum milliseconds between API calls
    max_retries: int = 5            # Maximum number of retries on 429
    max_backoff_seconds: int = 60   # Upper bound for exponential backoff wait
    connect_timeout: float = 10.0   # Connection timeout in seconds
    read_timeout: float = 30.0      # Read timeout in seconds
    write_timeout: float = 30.0     # Write timeout in seconds
    pool_timeout: float = 10.0      # Pool timeout in seconds


class RateLimiter:
    """
    Controls API call frequency and handles 429 rate-limit responses
    with exponential backoff retry.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()

    async def call_with_rate_limit(
        self,
        coro_func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Call an async coroutine function with rate limiting and retry logic.

        - Waits `interval_ms` milliseconds before each call.
        - On HTTP 429, retries up to `max_retries` times with exponential backoff.
        - On connection errors, retries up to `max_retries` times with exponential backoff.
        - Re-raises the last exception if all retries are exhausted.
        """
        # Pre-call interval to avoid bursting
        await asyncio.sleep(self.config.interval_ms / 1000.0)

        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await coro_func(*args, **kwargs)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    if attempt < self.config.max_retries:
                        wait = self._exponential_backoff(attempt)
                        logger.warning(
                            "Rate limited (429). Attempt %d/%d. Waiting %.1fs before retry.",
                            attempt + 1,
                            self.config.max_retries,
                            wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "Rate limit retries exhausted after %d attempts.",
                            self.config.max_retries,
                        )
                        raise
                else:
                    raise
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                # Handle connection-related errors with exponential backoff
                last_exc = exc
                if attempt < self.config.max_retries:
                    wait = self._exponential_backoff(attempt)
                    logger.warning(
                        "Connection failed (%s). Attempt %d/%d. Waiting %.1fs before retry.",
                        exc.__class__.__name__,
                        attempt + 1,
                        self.config.max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Connection retries exhausted after %d attempts.",
                        self.config.max_retries,
                    )
                    raise

        # Should not reach here, but satisfy type checker
        if last_exc is not None:
            raise last_exc

    def _exponential_backoff(self, attempt: int) -> float:
        """
        Return the wait time in seconds for a given retry attempt.

        Formula: min(2 ** attempt, max_backoff_seconds)
        """
        return float(min(2**attempt, self.config.max_backoff_seconds))
