"""
Engram — PII Masking Service (Step 6)
Scans text for PII before storage, replaces with tokens.
Real values stored in an in-memory vault (PostgreSQL vault comes later).

"""
import uuid
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# ── Load engines once ─────────────────────────
_analyzer = AnalyzerEngine()
_anonymizer = AnonymizerEngine()

# ── In-memory vault: token → original value ───
# Format: { "[PII_PERSON_a1b2c3d4]": "John Smith" }
_vault: dict[str, str] = {}

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


def mask(text: str) -> tuple[str, dict[str, str]]:
    """
    Scan text for PII and replace with tokens.

    Returns:
        masked_text: text safe to store in vector DB
        token_map:   { token: original_value } for this input
    """
    results = _analyzer.analyze(text=text, language="en", entities=PII_ENTITIES)

    if not results:
        return text, {}

    # Build a unique token per detected PII span
    token_map: dict[str, str] = {}
    operators: dict[str, OperatorConfig] = {}

    for result in results:
        token = f"[PII_{result.entity_type}_{uuid.uuid4().hex[:8]}]"
        original = text[result.start:result.end]
        token_map[token] = original
        operators[result.entity_type] = OperatorConfig("replace", {"new_value": token})

    anonymized = _anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators
    )

    # Save to vault
    _vault.update(token_map)

    return anonymized.text, token_map


def restore(masked_text: str, token_map: dict[str, str]) -> str:
    """Restore original PII values from a token map."""
    result = masked_text
    for token, original in token_map.items():
        result = result.replace(token, original)
    return result


def has_pii(text: str) -> bool:
    """Quick check — does this text contain any PII?"""
    results = _analyzer.analyze(text=text, language="en", entities=PII_ENTITIES)
    return len(results) > 0