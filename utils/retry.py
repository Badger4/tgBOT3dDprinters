"""
Lightweight async retry decorator with exponential backoff for network calls (FTPS/MQTT/Camera/AI).
Zero external dependencies, optimized for low memory footprint on Raspberry Pi.
"""
import asyncio
import functools
from typing import Callable, Any, Tuple, Type
from config import logger

def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,)
) -> Callable:
    """Decorator to retry an async function upon exception with exponential delay."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries:
                        logger.error(f"❌ [{func.__name__}] Failed after {retries} attempts: {e}")
                        raise
                    logger.warning(
                        f"⚠️ [{func.__name__}] Attempt {attempt}/{retries} failed ({e}). Retrying in {current_delay:.1f}s..."
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator
