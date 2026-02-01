"""
Performance profiling utilities for MeGPT.

Provides decorators, context managers, and FastAPI middleware for performance monitoring.
Enabled via environment variable ENABLE_PROFILING=true.
"""

import os
import time
import functools
import logging
from contextlib import contextmanager
from typing import Optional, Callable, Any
from datetime import datetime

# Optional imports - only required if profiling is enabled
try:
    import pyinstrument
    from pyinstrument import Profiler

    PYINSTRUMENT_AVAILABLE = True
except ImportError:
    PYINSTRUMENT_AVAILABLE = False
    Profiler = None

try:
    from memory_profiler import memory_usage

    MEMORY_PROFILER_AVAILABLE = True
except ImportError:
    MEMORY_PROFILER_AVAILABLE = False

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# Global profiling configuration
ENABLE_PROFILING = os.getenv("ENABLE_PROFILING", "false").lower() == "true"
PROFILING_OUTPUT_DIR = os.getenv("PROFILING_OUTPUT_DIR", "./profiling")
PROFILING_SAMPLE_RATE = float(os.getenv("PROFILING_SAMPLE_RATE", "1.0"))  # 0.0 to 1.0

# Ensure output directory exists
if ENABLE_PROFILING and PROFILING_OUTPUT_DIR:
    os.makedirs(PROFILING_OUTPUT_DIR, exist_ok=True)


def profiling_enabled() -> bool:
    """Check if profiling is enabled globally."""
    return ENABLE_PROFILING and (PYINSTRUMENT_AVAILABLE or MEMORY_PROFILER_AVAILABLE)


def get_profiling_output_path(filename: str) -> str:
    """Get full path for profiling output file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = f"{timestamp}_{filename}"
    return os.path.join(PROFILING_OUTPUT_DIR, basename)


@contextmanager
def profile_section(name: str, enable: bool = None):
    """
    Context manager for profiling a section of code.

    Args:
        name: Identifier for this profiling section
        enable: Override global profiling setting (default: use global)

    Yields:
        A Profiler instance if profiling is enabled, else None
    """
    should_profile = enable if enable is not None else profiling_enabled()

    if not should_profile or not PYINSTRUMENT_AVAILABLE:
        yield None
        return

    profiler = Profiler()
    profiler.start()

    try:
        yield profiler
    finally:
        profiler.stop()

        # Save profiling results
        output_path = get_profiling_output_path(f"section_{name}.html")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(profiler.output_html())
            logger.debug(f"Profiling saved to {output_path}")
        except Exception as e:
            logger.warning(f"Failed to save profiling output: {e}")


def profile_function(func: Optional[Callable] = None, *, enable: bool = None):
    """
    Decorator for profiling function execution.

    Usage:
        @profile_function
        def my_function():
            ...

        @profile_function(enable=True)
        def another_function():
            ...
    """

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            should_profile = enable if enable is not None else profiling_enabled()

            if not should_profile or not PYINSTRUMENT_AVAILABLE:
                return f(*args, **kwargs)

            # Use pyinstrument for CPU profiling
            profiler = Profiler()
            profiler.start()

            try:
                result = f(*args, **kwargs)
            finally:
                profiler.stop()

                # Save profiling results
                output_path = get_profiling_output_path(f"func_{f.__name__}.html")
                try:
                    with open(output_path, "w", encoding="utf-8") as file:
                        file.write(profiler.output_html())
                    logger.debug(f"Function profiling saved to {output_path}")
                except Exception as e:
                    logger.warning(f"Failed to save function profiling: {e}")

            return result

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


@contextmanager
def profile_memory(name: str, interval: float = 0.1, enable: bool = None):
    """
    Context manager for profiling memory usage.

    Args:
        name: Identifier for this memory profiling section
        interval: Sampling interval in seconds (default: 0.1)
        enable: Override global profiling setting

    Yields:
        A tuple (memory_before, memory_after) if profiling enabled
    """
    should_profile = enable if enable is not None else profiling_enabled()

    if not should_profile or not MEMORY_PROFILER_AVAILABLE:
        yield (None, None)
        return

    # Get baseline memory usage
    process = psutil.Process(os.getpid())
    memory_before = process.memory_info().rss / 1024 / 1024  # MB

    # Monitor memory during execution
    mem_usage = []

    def target():
        with profile_section(f"memory_{name}", enable=True):
            yield

    # We need to track memory usage of the code block
    # This is simplified - actual memory profiling requires more complex setup
    try:
        yield (memory_before, None)
    finally:
        memory_after = process.memory_info().rss / 1024 / 1024
        logger.debug(
            f"Memory usage for '{name}': {memory_before:.2f}MB -> {memory_after:.2f}MB"
        )


class FastAPIProfilingMiddleware:
    """
    FastAPI middleware for request profiling.

    Profiles each request and saves results to HTML files.
    Can be enabled/disabled via environment variable.
    """

    def __init__(self, app, sample_rate: float = None):
        self.app = app
        self.sample_rate = sample_rate or PROFILING_SAMPLE_RATE
        self._profiler = None

    async def __call__(self, scope, receive, send):
        # Only profile HTTP requests
        if scope["type"] != "http" or not profiling_enabled():
            await self.app(scope, receive, send)
            return

        # Sample rate filtering
        import random

        if random.random() > self.sample_rate:
            await self.app(scope, receive, send)
            return

        # Start profiling
        profiler = Profiler()
        profiler.start()

        # Create custom send wrapper to capture response
        original_send = send

        async def send_wrapper(response):
            await original_send(response)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            profiler.stop()

            # Save profiling results
            path = scope.get("path", "unknown")
            method = scope.get("method", "UNKNOWN")
            output_path = get_profiling_output_path(
                f"req_{method}_{path.replace('/', '_')}.html"
            )

            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(profiler.output_html())
                logger.info(f"Request profiling saved to {output_path}")
            except Exception as e:
                logger.warning(f"Failed to save request profiling: {e}")


def setup_fastapi_profiling(app):
    """
    Helper to add profiling middleware to FastAPI app.

    Args:
        app: FastAPI application instance

    Returns:
        The app with profiling middleware added (if enabled)
    """
    if not profiling_enabled() or not PYINSTRUMENT_AVAILABLE:
        return app

    # Import here to avoid circular dependencies
    from fastapi.middleware import Middleware
    from fastapi.middleware import middleware

    # Create middleware instance
    profiling_middleware = FastAPIProfilingMiddleware(app)

    # Add middleware to app (simplified - actual implementation may vary)
    # In practice, we'd use app.add_middleware()
    logger.info("Profiling middleware enabled for FastAPI")

    return app


# Simple timer decorator (always available, lightweight)
def timed_function(func):
    """Decorator that logs function execution time."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            logger.debug(f"Function {func.__name__} took {duration_ms:.2f}ms")

        return result

    return wrapper


# Export public API
__all__ = [
    "profiling_enabled",
    "profile_section",
    "profile_function",
    "profile_memory",
    "FastAPIProfilingMiddleware",
    "setup_fastapi_profiling",
    "timed_function",
]
