"""
Engram — Bio-Mimetic Memory Retention Scoring

Implements the Ebbinghaus Forgetting Curve augmented with reinforcement,
matching HydraDB's Bio-Mimetic Decay Engine described in their paper.

Retention score formula:
  R(m, t) = salience × e^(−λ × Δt_days) + σ × Σ(1 / (t − t_access_i))

Where:
  salience    — initial importance of the memory (high for identity/medical facts,
                lower for routine mentions)
  λ           — decay rate (controls half-life, configurable via RETENTION_DECAY_RATE)
  Δt_days     — days elapsed since the memory was first stored
  σ           — reinforcement scaling factor (RETENTION_ACCESS_BOOST)
  t_access_i  — timestamp of each previous successful retrieval

"""
import json
import math
from datetime import datetime, timezone
from db import get_redis
from config import get_settings

settings = get_settings()

# ── Salience classification patterns ─────────────────────────────
# High salience: facts that matter long-term regardless of access frequency
HIGH_SALIENCE_PATTERNS = [
    "allerg", "medical", "medication", "diagnosis", "condition",
    "born", "birthday", "anniversary",
    "married", "partner", "spouse", "child", "parent",
    "name is", "my name", "i am",
    "works at", "job", "career", "profession",
    "lives in", "home", "address",
    "religion", "belief", "value",
    "graduated", "degree", "university", "education",
    "password", "secret",
]


def _salience_high() -> float:
    try:
        return settings.retention_salience_high
    except AttributeError:
        return 1.0


def _salience_low() -> float:
    try:
        return settings.retention_salience_low
    except AttributeError:
        return 0.5


def _classify_salience(content: str) -> float:
    """
    Assign initial salience score based on content.
    High-salience facts resist decay more than routine ones.
    """
    lower = content.lower()
    for pattern in HIGH_SALIENCE_PATTERNS:
        if pattern in lower:
            return _salience_high()
    return _salience_low()


def _decay_rate() -> float:
    try:
        return settings.retention_decay_rate
    except AttributeError:
        return 0.01


def _access_boost() -> float:
    try:
        return settings.retention_access_boost
    except AttributeError:
        return 0.1


def _forget_threshold() -> float:
    try:
        return settings.retention_forget_threshold
    except AttributeError:
        return 0.0


def _redis_key(memory_id: str) -> str:
    return f"retention:{memory_id}:meta"


def _now_ts() -> float:
    """Current UTC timestamp as float seconds."""
    return datetime.now(timezone.utc).timestamp()


# ── Write operations ──────────────────────────────────────────────

def init_retention(memory_id: str, content: str):
    """
    Called when a memory is first stored. Initialises the retention
    metadata in Redis: salience, creation time, empty access log.

    Non-blocking — Redis failures are silently swallowed so the store
    pipeline never fails due to retention issues.
    """
    try:
        r = get_redis()
        salience = _classify_salience(content)
        meta = {
            "salience":    salience,
            "created_at":  _now_ts(),
            "access_times": [],
        }
        r.set(_redis_key(memory_id), json.dumps(meta))
        print(f"[Engram:Retention] Init [{memory_id[:8]}] salience={salience:.1f}")
    except Exception as e:
        print(f"[Engram:Retention] init_retention failed (non-critical): {e}")


def record_access(memory_id: str):
    """
    Called when a memory is successfully retrieved (recall hit).
    Appends the current timestamp to the access log — this is the
    reinforcement signal that resets the decay curve.

    Keeps only the last 20 access times to bound Redis memory usage.
    """
    try:
        r   = get_redis()
        key = _redis_key(memory_id)
        raw = r.get(key)
        if not raw:
            return  # memory has no retention meta — skip silently

        meta = json.loads(raw)
        times = meta.get("access_times", [])
        times.append(_now_ts())
        meta["access_times"] = times[-20:]  # keep last 20 accesses
        r.set(key, json.dumps(meta))
    except Exception as e:
        print(f"[Engram:Retention] record_access failed (non-critical): {e}")


# ── Score computation ─────────────────────────────────────────────

def compute_score(memory_id: str) -> float:
    """
    Compute the current retention score R(m, t) for a memory.

    R = salience × e^(−λ × Δt_days) + σ × Σ(1 / (t_now − t_access_i + 1))

    The +1 in the denominator prevents division-by-zero for very recent
    accesses and bounds the reinforcement term.

    Returns:
        Score between 0.0 and ~(salience + σ×N). Higher = more retained.
        Returns 1.0 (fully retained) if no metadata found — fail-safe so
        missing metadata never causes memories to be incorrectly filtered.
    """
    try:
        r   = get_redis()
        raw = r.get(_redis_key(memory_id))
        if not raw:
            return 1.0  # no metadata → treat as fully retained

        meta         = json.loads(raw)
        salience     = float(meta.get("salience", _salience_high()))
        created_at   = float(meta.get("created_at", _now_ts()))
        access_times = meta.get("access_times", [])

        now        = _now_ts()
        delta_days = (now - created_at) / 86400.0

        decay = salience * math.exp(-_decay_rate() * delta_days)

        boost = 0.0
        for t_access in access_times:
            elapsed_days = (now - t_access) / 86400.0
            boost += _access_boost() / (elapsed_days + 1.0)

        score = decay + boost
        return round(score, 4)

    except Exception as e:
        print(f"[Engram:Retention] compute_score failed (non-critical): {e}")
        return 1.0  # fail-safe


def is_forgotten(memory_id: str) -> bool:
    """
    Returns True if the memory's retention score has fallen below the
    forget_threshold. When True, the memory should be excluded from
    recall results (but never deleted from storage).

    Always returns False if forget_threshold == 0.0 (disabled).
    """
    if _forget_threshold() <= 0.0:
        return False
    return compute_score(memory_id) < _forget_threshold()


# ── Batch operations ──────────────────────────────────────────────

def filter_by_retention(memories: list[dict]) -> list[dict]:
    """
    Filter a list of memory dicts, removing those whose retention score
    has fallen below the forget_threshold.

    Also records an access event for every memory that passes the filter
    (= successfully retrieved), which boosts their retention score.

    Args:
        memories: List of memory dicts with at least an "id" key.

    Returns:
        Filtered list. If retention is disabled (threshold=0), returns
        the original list unchanged (but still records accesses).
    """
    result = []
    for memory in memories:
        mid = memory.get("id", "")
        if not mid:
            result.append(memory)
            continue

        if is_forgotten(mid):
            score = compute_score(mid)
            print(
                f"[Engram:Retention] Filtering [{mid[:8]}] "
                f"(score={score:.3f} < threshold={_forget_threshold()})"
            )
            continue

        record_access(mid)

        memory = {**memory, "retention_score": compute_score(mid)}
        result.append(memory)

    return result


def get_retention_stats(memory_ids: list[str]) -> list[dict]:
    """
    Return retention scores for a list of memory IDs.
    Used by the admin/health dashboard to show memory health.
    """
    stats = []
    for mid in memory_ids:
        score = compute_score(mid)
        threshold = _forget_threshold()
        stats.append({
            "id":       mid,
            "score":    score,
            "forgotten": score < threshold if threshold > 0 else False,
        })
    return sorted(stats, key=lambda x: x["score"])
