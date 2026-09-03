"""Rate limiting configuration using SlowAPI."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def rate_limit_key_func(request: Request) -> str:
    """Extract rate limit key: prefer Bearer token prefix, fallback to IP."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer agb_live_"):
        # Bucket by the API key prefix
        return auth[:25]
    return get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key_func, default_limits=["120/minute"])
