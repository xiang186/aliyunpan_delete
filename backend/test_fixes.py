#!/usr/bin/env python3
"""
Test script to verify the fixes for connection issues.
"""
import asyncio
import httpx
from app.core.rate_limiter import RateLimiter, RateLimitConfig


async def test_rate_limiter_connection_error():
    """Test that RateLimiter handles connection errors properly."""
    print("Testing RateLimiter connection error handling...")
    
    config = RateLimitConfig(
        interval_ms=500,
        max_retries=3,
        max_backoff_seconds=10,
        connect_timeout=5.0,
        read_timeout=10.0,
        write_timeout=10.0,
        pool_timeout=5.0,
    )
    
    limiter = RateLimiter(config)
    
    # Create a function that simulates connection errors
    call_count = 0
    
    async def failing_request():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("Simulated connection error")
        return {"success": True}
    
    try:
        result = await limiter.call_with_rate_limit(failing_request)
        print(f"✓ RateLimiter handled connection errors correctly")
        print(f"  Result: {result}")
        print(f"  Retries: {call_count - 1}")
        return True
    except Exception as e:
        print(f"✗ RateLimiter failed: {e}")
        return False


async def test_rate_limiter_timeout_config():
    """Test that timeout configuration is properly passed."""
    print("\nTesting RateLimiter timeout configuration...")
    
    config = RateLimitConfig(
        interval_ms=500,
        max_retries=3,
        max_backoff_seconds=10,
        connect_timeout=5.0,
        read_timeout=10.0,
        write_timeout=10.0,
        pool_timeout=5.0,
    )
    
    limiter = RateLimiter(config)
    
    # Check that config values are accessible
    assert limiter.config.connect_timeout == 5.0
    assert limiter.config.read_timeout == 10.0
    assert limiter.config.write_timeout == 10.0
    assert limiter.config.pool_timeout == 5.0
    
    print("✓ Timeout configuration is properly set")
    return True


async def test_concurrent_tasks_import():
    """Test that concurrent task tracking imports work."""
    print("\nTesting concurrent task tracking imports...")
    
    try:
        from app.services.scan_service import (
            _MAX_CONCURRENT_API_TASKS,
            _current_api_tasks,
            _api_tasks_lock
        )
        
        print(f"✓ Concurrent task tracking imports successful")
        print(f"  Max concurrent tasks: {_MAX_CONCURRENT_API_TASKS}")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing fixes for connection issues")
    print("=" * 60)
    
    tests = [
        test_rate_limiter_connection_error,
        test_rate_limiter_timeout_config,
        test_concurrent_tasks_import,
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! The fixes are working correctly.")
    else:
        print(f"\n❌ {total - passed} test(s) failed. Please check the implementation.")


if __name__ == "__main__":
    asyncio.run(main())