"""Retry and fault tolerance utilities."""

import asyncio
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, Type, TypeVar

import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    min_wait_seconds: float = 1.0
    max_wait_seconds: float = 10.0
    exponential_base: float = 2.0
    retry_exceptions: tuple[Type[Exception], ...] = (Exception,)


async def with_retry(
    func: Callable[..., T],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> T:
    """
    Execute an async function with retry logic.

    Args:
        func: The async function to execute
        *args: Positional arguments for the function
        config: Retry configuration (uses defaults if not provided)
        **kwargs: Keyword arguments for the function

    Returns:
        The result of the function

    Raises:
        RetryError: If all retry attempts fail
    """
    config = config or RetryConfig()

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(config.max_attempts),
        wait=wait_exponential(
            multiplier=config.min_wait_seconds,
            max=config.max_wait_seconds,
            exp_base=config.exponential_base,
        ),
        retry=retry_if_exception_type(config.retry_exceptions),
        reraise=True,
    ):
        with attempt:
            logger.debug(
                "Executing with retry",
                function=func.__name__,
                attempt=attempt.retry_state.attempt_number,
                max_attempts=config.max_attempts,
            )
            return await func(*args, **kwargs)

    # This should never be reached due to reraise=True
    raise RuntimeError("Unexpected state in retry logic")


def retry_decorator(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    retry_on: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Decorator for adding retry logic to async functions.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        retry_on: Tuple of exception types to retry on

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            config = RetryConfig(
                max_attempts=max_attempts,
                min_wait_seconds=min_wait,
                max_wait_seconds=max_wait,
                retry_exceptions=retry_on,
            )
            return await with_retry(func, *args, config=config, **kwargs)

        return wrapper

    return decorator


class CircuitBreaker:
    """
    Simple circuit breaker implementation for fault tolerance.

    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Failing, requests are blocked
        - HALF_OPEN: Testing if service is recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "CLOSED"
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        return self._state

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Args:
            func: The async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            The result of the function

        Raises:
            CircuitBreakerOpen: If the circuit is open
            Exception: If the function raises an exception
        """
        async with self._lock:
            await self._check_state()

            if self._state == "OPEN":
                raise CircuitBreakerOpen(
                    f"Circuit breaker is open. Recovery in "
                    f"{self._time_until_recovery():.1f}s"
                )

        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            raise

    async def _check_state(self) -> None:
        """Check and potentially transition circuit breaker state."""
        if self._state == "OPEN":
            if self._time_until_recovery() <= 0:
                self._state = "HALF_OPEN"
                self._half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")

    def _time_until_recovery(self) -> float:
        """Calculate time until recovery from OPEN state."""
        if self._last_failure_time is None:
            return 0
        import time

        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == "HALF_OPEN":
                self._half_open_calls += 1
                if self._half_open_calls >= self.half_open_max_calls:
                    self._state = "CLOSED"
                    self._failure_count = 0
                    logger.info("Circuit breaker transitioning to CLOSED")
            else:
                self._failure_count = 0

    async def _record_failure(self) -> None:
        """Record a failed call."""
        import time

        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                logger.warning("Circuit breaker transitioning to OPEN from HALF_OPEN")
            elif self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning(
                    "Circuit breaker transitioning to OPEN",
                    failure_count=self._failure_count,
                )


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""

    pass
