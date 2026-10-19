"""Rate limiting configuration using SlowAPI and lightweight sliding-window protection."""

from collections import deque
import threading
import time
from typing import Deque, Dict, Tuple
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def rate_limit_key_func(request: Request) -> str:
    """Extract rate limit key: prefer Bearer token prefix or X-API-Key, fallback to IP."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[:32]
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key[:20]}"
    return get_remote_address(request) or "127.0.0.1"


class SlidingWindowRateLimiter:
    """Lightweight in-memory sliding-window rate limiter for gateway and MCP endpoints."""

    def __init__(self, max_requests: int = 240, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check_and_consume(self, key: str) -> Tuple[bool, int, float]:
        """
        Return (allowed, remaining_quota, retry_after_seconds).
        Executes in O(1) amortized time without blocking the event loop.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(0.1, round(self.window_seconds - (now - bucket[0]), 2))
                return False, 0, retry_after

            bucket.append(now)
            remaining = max(0, self.max_requests - len(bucket))
            return True, remaining, 0.0


limiter = Limiter(key_func=rate_limit_key_func, default_limits=["120/minute"])
gateway_rate_limiter = SlidingWindowRateLimiter(max_requests=240, window_seconds=60.0)

