"""
Engram — TTL / Auto-Forget (Step 10)
Detects time-sensitive facts and sets Redis TTL for auto-expiry.
Stale memories like "meeting tomorrow" poisoning recall forever.
"""
import re
from db import get_redis
from datetime import datetime, timedelta, timezone
from config import get_settings

settings = get_settings()

TIME_PATTERNS = [
    (r"\btoday\b",              timedelta(hours=24)),
    (r"\btonight\b",            timedelta(hours=12)),
    (r"\btomorrow\b",           timedelta(days=2)),
    (r"\bthis week\b",          timedelta(weeks=1)),
    (r"\bnext week\b",          timedelta(weeks=2)),
    (r"\bthis month\b",         timedelta(days=35)),
    (r"\bnext month\b",         timedelta(days=65)),
    (r"\bdeadline\b",           timedelta(days=30)),
    (r"\bdue date\b",           timedelta(days=30)),
    (r"\bappointment\b",        timedelta(days=7)),
    (r"\breminder\b",           timedelta(days=3)),
    (r"\bexpires?\b",           timedelta(days=14)),
    (r"\btemporarily\b",        timedelta(days=7)),
    (r"\bfor now\b",            timedelta(days=3)),
    (r"\buntil further notice\b", timedelta(days=30)),
    (r"\bon [a-z]+ \d{1,2}(st|nd|rd|th)?\b", timedelta(days=14)),  # "on Monday 3rd"
]

PERMANENT_PATTERNS = [
    r"\balways\b",
    r"\bnever\b",
    r"\bforever\b",
    r"\bpermanent\b",
    r"\bpolicy\b",
    r"\bconvention\b",
    r"\bdecided\b",
    r"\bagreed\b",
    r"\bstandard\b",
    r"\btradition\b",
    r"\bhabit\b",
    r"\busually\b",
    r"\bgenerally\b",
    r"\btypically\b",
    r"\bworks? at\b",       
    r"\blives? in\b",       
    r"\bborn in\b",        
    r"\bgraduated\b",       
    r"\bmarried\b",         
]


def get_expiry(content: str, is_temporary_hint: bool | None = None) -> datetime | None:
    """
    Returns expiry datetime if fact is time-sensitive, None if permanent.

    Args:
        content:           The fact text to classify.
        is_temporary_hint: Value from the LLM extractor. True = temporary,
                           False = permanent, None = extractor was uncertain.

    Priority:
        1. LLM says temporary  → honour it, use 7-day default
        2. LLM says permanent  → honour it, skip all regex
        3. Permanent phrase    → permanent
        4. Time-anchor pattern → temporary with specific delta
        5. Default             → permanent
    """
    # ── 1. Trust the LLM extractor first ─────────────────────────
    if is_temporary_hint is True:
        return _now() + timedelta(days=7)
    if is_temporary_hint is False:
        return None  

    # ── 2. Extractor was uncertain (hint=None) — fall back to rules ─
    text = content.lower()

    # ── 3. Permanent-phrase override ──────────────────────────────
    for pattern in PERMANENT_PATTERNS:
        if re.search(pattern, text):
            return None

    # ── 4. Time-anchor pattern match ──────────────────────────────
    for pattern, delta in TIME_PATTERNS:
        if re.search(pattern, text):
            return _now() + delta

    # ── 5. Default: permanent ─────────────────────────────────────
    return None


def _now() -> datetime:
    """UTC now without tzinfo (consistent with existing storage format)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def set_ttl(memory_id: str, expires_at: datetime):
    """
    Store expiry in Redis.

    Writes two keys:
      ttl:{id}     — expires automatically when TTL fires (Redis SETEX)
      ttl_set:{id} — permanent sentinel, never expires, marks that this
                     memory was ever given a TTL

    This lets is_expired() distinguish:
      "never had a TTL" (permanent)  → ttl_set key missing
      "had a TTL that fired"         → ttl_set present, ttl key gone
    """
    r = get_redis()
    ttl_seconds = int((expires_at - _now()).total_seconds())
    if ttl_seconds <= 0:
        print(f"[Engram] TTL skipped [{memory_id[:8]}]: expiry already in the past")
        return

    ttl_seconds += 1
    pipe = r.pipeline()
    pipe.setex(f"ttl:{memory_id}", ttl_seconds, expires_at.isoformat())
    pipe.set(f"ttl_set:{memory_id}", expires_at.isoformat())   # permanent sentinel
    pipe.execute()
    print(f"[Engram] TTL set [{memory_id[:8]}]: expires in {ttl_seconds}s ({expires_at.strftime('%Y-%m-%d %H:%M')} UTC)")


def is_expired(memory_id: str) -> bool:
    """
    Check if a memory's TTL has expired.

    Logic using the two-key approach:
      ttl_set key missing          → memory was never given a TTL → permanent, NOT expired
      ttl_set present, ttl present → countdown still active → NOT expired
      ttl_set present, ttl gone   → Redis auto-deleted the ttl key → EXPIRED

    Fail-open: if Redis is unreachable, treat all as not expired so
    recall still works (degraded, not broken).
    """
    r = get_redis()
    try:
        pipe = r.pipeline()
        pipe.exists(f"ttl_set:{memory_id}")  
        pipe.ttl(f"ttl:{memory_id}")           
        ttl_set_exists, ttl = pipe.execute()

        if not ttl_set_exists:
            return False  

        
        if ttl == -2:
            return True    
        if ttl == -1:
            return False   # ttl key has no expiry (shouldn't happen) → treat as permanent
        if ttl > 0:
            return False   
        return True        

    except Exception:
        return False  


def get_ttl_seconds(memory_id: str) -> int | None:
    """Get remaining TTL in seconds. Returns None if permanent or not set."""
    r = get_redis()
    ttl = r.ttl(f"ttl:{memory_id}")
    if ttl in (-1, -2):
        return None
    return ttl
