"""
Engram — PII Masking Service
Scans text for PII before storage, replaces with tokens.
Real values persisted in PostgreSQL pii_vault table.
In-memory cache layer avoids redundant DB reads.
"""
import uuid
from db import get_pg
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from config import get_settings

settings = get_settings()

# ── Load engines once ─────────────────────────
_analyzer  = AnalyzerEngine()
_anonymizer = AnonymizerEngine()

# ── In-memory cache: token → original value ───
# Populated from DB on restore() if not cached locally.
_cache: dict[str, str] = {}

PII_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "LOCATION",
    "DATE_TIME",
    "IP_ADDRESS",
    "URL",
    "IBAN_CODE",
    "MEDICAL_LICENSE",
]


def _pg_conn():
    return get_pg()


def _save_to_db(token: str, original: str, pii_type: str):
    """Persist a token → original mapping to PostgreSQL."""
    try:
        conn = _pg_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO pii_vault (token, original_value, pii_type)
               VALUES (%s, %s, %s)
               ON CONFLICT (token) DO NOTHING""",
            (token, original, pii_type),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[Engram:PII] DB save failed (non-critical): {e}")


def _load_from_db(token: str) -> str | None:
    """Look up a token in PostgreSQL. Returns original value or None."""
    try:
        conn = _pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT original_value FROM pii_vault WHERE token = %s", (token,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"[Engram:PII] DB load failed: {e}")
        return None


# ── Public API ────────────────────────────────

def mask(text: str) -> tuple[str, dict[str, str]]:
    """
    Scan text for PII and replace with tokens.
    Tokens and original values are saved to PostgreSQL for persistence
    across restarts.

    Returns:
        masked_text: text safe to store in vector DB
        token_map:   { token: original_value } for this input
    """
    results = _analyzer.analyze(text=text, language="en", entities=PII_ENTITIES)

    if not results:
        return text, {}

    token_map: dict[str, str] = {}
    operators: dict[str, OperatorConfig] = {}

    for result in results:
        token    = f"[PII_{result.entity_type}_{uuid.uuid4().hex[:8]}]"
        original = text[result.start:result.end]
        token_map[token] = original
        operators[result.entity_type] = OperatorConfig("replace", {"new_value": token})

    anonymized = _anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators,
    )

    # Persist each token to DB and update in-memory cache
    for token, original in token_map.items():
        pii_type = next(
            (r.entity_type for r in results
             if text[r.start:r.end] == original),
            "UNKNOWN",
        )
        _cache[token] = original
        _save_to_db(token, original, pii_type)

    return anonymized.text, token_map


def restore(masked_text: str, token_map: dict[str, str] | None = None) -> str:
    """
    Restore original PII values in masked_text.
    Uses token_map if provided (same-session restore).
    Falls back to DB lookup for tokens not in token_map (cross-session restore).
    """
    result = masked_text

    # Collect all tokens present in the text
    import re
    tokens_in_text = re.findall(r'\[PII_[A-Z_]+_[0-9a-f]{8}\]', result)

    for token in tokens_in_text:
        # 1. Try provided token_map
        original = (token_map or {}).get(token)
        # 2. Try in-memory cache
        if not original:
            original = _cache.get(token)
        # 3. Try DB
        if not original:
            original = _load_from_db(token)
            if original:
                _cache[token] = original  # warm the cache
        if original:
            result = result.replace(token, original)

    return result


def has_pii(text: str) -> bool:
    """Quick check — does this text contain any PII?"""
    results = _analyzer.analyze(text=text, language="en", entities=PII_ENTITIES)
    return len(results) > 0
