"""
Unit tests for utils/retry.py async_retry decorator.
"""

import asyncio
import pytest
from utils.retry import async_retry


@pytest.mark.asyncio
async def test_async_retry_success_first_try():
    call_count = 0

    @async_retry(retries=3, delay=0.01, backoff=1.0)
    async def sample_func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await sample_func()
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_async_retry_success_after_retries():
    call_count = 0

    @async_retry(retries=3, delay=0.01, backoff=1.0, exceptions=(ValueError,))
    async def sample_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Temporary failure")
        return "recovered"

    result = await sample_func()
    assert result == "recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_retry_exhaust_retries_raises():
    call_count = 0

    @async_retry(retries=2, delay=0.01, backoff=1.0, exceptions=(KeyError,))
    async def sample_func():
        nonlocal call_count
        call_count += 1
        raise KeyError("Persistent failure")

    with pytest.raises(KeyError):
        await sample_func()

    assert call_count == 2
