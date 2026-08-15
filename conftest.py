"""
Global pytest configuration and fixtures for deterministic async test execution.
"""

import asyncio

import pytest


@pytest.fixture(autouse=True)
async def cleanup_pending_tasks():
    """
    Ensures that any background coroutines, stream loops, or pending tasks
    spawned during a test are explicitly cancelled and awaited upon test completion.
    """
    yield
    try:
        current = asyncio.current_task()
        pending = [t for t in asyncio.all_tasks() if not t.done() and t is not current]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    except RuntimeError:
        # Loop may already be closed in some unittest test runners
        pass
