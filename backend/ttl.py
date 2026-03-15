"""
Engram — TTL / Auto-Forget (Step 10)
Detects time-sensitive facts and sets Redis TTL for auto-expiry.
Stale memories like "meeting tomorrow" poisoning recall forever.
"""
import re
import redis
from datetime import datetime, timedelta, timezone
from config import get_settings

settings = get_settings()

# Patterns → expiry delta
TIME_PATTERNS = [
    (r"\btoday\b",          timedelta(hours=24)),
    (r"\btonight\b",        timedelta(hours=12)),
    (r"\btomorrow\b",       timedelta(days=2)),
    (r"\bthis week\b",      timedelta(weeks=1)),
    (r"\bnext week\b",      timedelta(weeks=2)),
    (r"\bthis month\b",     timedelta(days=35)),
    (r"\bnext month\b",     timedelta(days=65)),
    (r"\bdeadline\b",       timedelta(days=30)),
    (r"\bdue date\b",       timedelta(days=30)),
    (r"\bmeeting\b",        timedelta(days=7)),
    (r"\bappointment\b",    timedelta(days=7)),
    (r"\breminder\b",       timedelta(days=3)),
    (r"\bexpires?\b",       timedelta(days=14)),
    (r"\btemporarily\b",    timedelta(days=7)),
    (r"\bfor now\b",        timedelta(days=3)),
    (r"\bcurrently\b",      timedelta(days=90)),
]

# These words make a fact permanent regardless
PERMANENT_PATTERNS = [
    r"\balways\b", r"\bnever\b", r"\bforever\b",
    r"\bpermanent\b", r"\bpolicy\b", r"\bconvention\b",
    r"\bdecided\b", r"\bagreed\b", r"\bstandard\b",
]


def get_expiry(content: str, is_temporary_hint: bool = None) -> datetime | None:
    """
    Returns expiry datetime if fact is time-sensitive, None if permanent.
    is_temporary_hint: override from fact extractor if available.
    """
    text = content.lower()

    # Permanent override
    for pattern in PERMANENT_PATTERNS:
        if re.search(pattern, text):
            return None

    # Use hint from extractor if available
    if is_temporary_hint is True:
        return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
    if is_temporary_hint is False:
        return None

    # Auto-detect from patterns
    for pattern, delta in TIME_PATTERNS:
        if re.search(pattern, text):
            return datetime.now(timezone.utc).replace(tzinfo=None) + delta

    return None  # permanent by default


def set_ttl(memory_id: str, expires_at: datetime):
    """Store expiry in Redis. Redis auto-deletes the key when TTL runs out."""
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    ttl_seconds = int((expires_at - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
    r.setex(f"ttl:{memory_id}", ttl_seconds, expires_at.isoformat())
    print(f"[Engram] TTL set [{memory_id[:8]}]: expires in {ttl_seconds}s ({expires_at.strftime('%Y-%m-%d %H:%M')} UTC)")


def is_expired(memory_id: str) -> bool:
    """Check if a memory's TTL has expired in Redis."""
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    return r.exists(f"ttl:{memory_id}") == 0


def get_ttl_seconds(memory_id: str) -> int | None:
    """Get remaining TTL in seconds. None if no TTL set (permanent)."""
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    ttl = r.ttl(f"ttl:{memory_id}")
    if ttl == -2:
        return None   # key doesn't exist — either expired or never had TTL
    if ttl == -1:
        return None   # no TTL set
    return ttl
