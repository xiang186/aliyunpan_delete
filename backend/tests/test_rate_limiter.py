"""
Unit and property-based tests for the RateLimiter.

**Validates: Requirements 8.1, 8.2, 8.3**
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.rate_limiter import RateLimitConfig, RateLimiter


# ---------------------------------------------------------------------------
# Unit tests – RateLimitConfig defaults
# ---------------------------------------------------------------------------


def test_rate_limit_config_defaults() -> None:
    config = RateLimitConfig()
    assert config.interval_ms == 200
    assert config.max_retries == 5
    assert config.max_backoff_seconds == 60


def test_rate_limit_config_custom() -> None:
    config = RateLimitConfig(interval_ms=100, max_retries=3, max_backoff_seconds=30)
    assert config.interval_ms == 100
    assert config.max_retries == 3
    assert config.max_backoff_seconds == 30


# ---------------------------------------------------------------------------
# Unit tests – _exponential_backoff
# ---------------------------------------------------------------------------


def test_exponential_backoff_attempt_0() -> None:
    limiter = RateLimiter()
    assert limiter._exponential_backoff(0) == 1.0  # 2^0 = 1


def test_exponential_backoff_attempt_1() -> None:
    limiter = RateLimiter()
    assert limiter._exponential_backoff(1) == 2.0  # 2^1 = 2


def test_exponential_backoff_attempt_5() -> None:
    limiter = RateLimiter()
    assert limiter._exponential_backoff(5) == 32.0  # 2^5 = 32


def test_exponential_backoff_capped_at_max() -> None:
    limiter = RateLimiter(RateLimitConfig(max_backoff_seconds=10))
    # 2^10 = 1024, but capped at 10
    assert limiter._exponential_backoff(10) == 10.0


def test_exponential_backoff_returns_float() -> None:
    limiter = RateLimiter()
    result = limiter._exponential_backoff(3)
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Unit tests – call_with_rate_limit (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_with_rate_limit_success(monkeypatch) -> None:
    """Successful call returns the coroutine's result."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def my_coro(x: int) -> int:
        return x * 2

    limiter = RateLimiter(RateLimitConfig(interval_ms=0))
    result = await limiter.call_with_rate_limit(my_coro, 5)
    assert result == 10


@pytest.mark.asyncio
async def test_call_with_rate_limit_waits_interval(monkeypatch) -> None:
    """The limiter sleeps for interval_ms / 1000 before calling."""
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def my_coro() -> str:
        return "ok"

    limiter = RateLimiter(RateLimitConfig(interval_ms=400))
    await limiter.call_with_rate_limit(my_coro)
    assert sleep_calls[0] == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_call_with_rate_limit_retries_on_429(monkeypatch) -> None:
    """On 429, the limiter retries up to max_retries times."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    call_count = 0

    def _make_429_response() -> httpx.Response:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        return response

    async def flaky_coro() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.HTTPStatusError(
                "rate limited", request=MagicMock(), response=_make_429_response()
            )
        return "success"

    limiter = RateLimiter(RateLimitConfig(interval_ms=0, max_retries=5))
    result = await limiter.call_with_rate_limit(flaky_coro)
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_call_with_rate_limit_raises_after_max_retries(monkeypatch) -> None:
    """After max_retries exhausted, the 429 error is re-raised."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    def _make_429_response() -> httpx.Response:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        return response

    async def always_429() -> None:
        raise httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=_make_429_response()
        )

    limiter = RateLimiter(RateLimitConfig(interval_ms=0, max_retries=3))
    with pytest.raises(httpx.HTTPStatusError):
        await limiter.call_with_rate_limit(always_429)


@pytest.mark.asyncio
async def test_call_with_rate_limit_non_429_not_retried(monkeypatch) -> None:
    """Non-429 HTTP errors are not retried and propagate immediately."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    call_count = 0

    def _make_500_response() -> httpx.Response:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        return response

    async def server_error() -> None:
        nonlocal call_count
        call_count += 1
        raise httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=_make_500_response()
        )

    limiter = RateLimiter(RateLimitConfig(interval_ms=0, max_retries=5))
    with pytest.raises(httpx.HTTPStatusError):
        await limiter.call_with_rate_limit(server_error)

    assert call_count == 1  # No retries for non-429


@pytest.mark.asyncio
async def test_call_with_rate_limit_passes_args_and_kwargs(monkeypatch) -> None:
    """Arguments and keyword arguments are forwarded to the coroutine."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def add(a: int, b: int = 0) -> int:
        return a + b

    limiter = RateLimiter(RateLimitConfig(interval_ms=0))
    result = await limiter.call_with_rate_limit(add, 3, b=7)
    assert result == 10


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

# Feature: aliyundrive-duplicate-cleaner, Property 9: 退避时间单调递增与上界约束


@given(st.integers(min_value=0, max_value=4))
@settings(max_examples=100)
def test_backoff_is_monotonically_increasing(attempt: int) -> None:
    """
    **Validates: Requirements 8.2**

    For any attempt n in [0, 4], wait(n) <= wait(n+1) (monotonically non-decreasing).
    """
    limiter = RateLimiter()
    assert limiter._exponential_backoff(attempt) <= limiter._exponential_backoff(attempt + 1)


@given(st.integers(min_value=0, max_value=100))
@settings(max_examples=100)
def test_backoff_never_exceeds_max(attempt: int) -> None:
    """
    **Validates: Requirements 8.2**

    For any attempt n, wait(n) <= max_backoff_seconds.
    """
    config = RateLimitConfig(max_backoff_seconds=60)
    limiter = RateLimiter(config)
    assert limiter._exponential_backoff(attempt) <= config.max_backoff_seconds


@given(st.integers(min_value=0, max_value=100))
@settings(max_examples=100)
def test_backoff_is_non_negative(attempt: int) -> None:
    """
    **Validates: Requirements 8.2**

    Backoff wait time is always non-negative.
    """
    limiter = RateLimiter()
    assert limiter._exponential_backoff(attempt) >= 0
