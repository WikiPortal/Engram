"""
Engram — Fact Extractor
Uses the configured LLM provider to extract clean atomic facts from raw input.
"""
import json
from llm import complete
from config import get_settings

settings = get_settings()


EXTRACT_PROMPT = """You are a fact extractor for a personal AI memory system.

Given input text, extract every distinct, atomic fact. Rules:
1. Each fact must be self-contained and specific
2. CRITICAL — capture negations correctly: "I don't like X" → "User dislikes X"
3. Replace pronouns with the actual entity where clear: "He leads backend" + context "John" → "John leads backend"
4. Mark time-sensitive facts: anything with today/tomorrow/next week/deadline/meeting = is_temporary true
5. Skip filler/pleasantries. Only real facts worth remembering.
6. Max 8 facts per input.

Return ONLY valid JSON, no markdown, no explanation:
{
  "facts": [
    {
      "content": "fact text here",
      "is_temporary": false,
      "confidence": 0.95,
      "tags": ["tag1", "tag2"]
    }
  ]
}"""

VALIDATE_PROMPT = """You are a fact validator for a personal AI memory system.

Given the original text and a list of extracted facts, verify each fact:
- Is it actually stated in the original text?
- Are negations captured correctly? ("don't like" should NOT become "likes")
- Is the attribution correct?

Remove any facts that are wrong or hallucinated.
Return ONLY valid JSON, no markdown:
{
  "facts": [
    {
      "content": "fact text here",
      "is_temporary": false,
      "confidence": 0.95,
      "tags": ["tag1"]
    }
  ]
}"""


def _call_llm(system: str, user_message: str) -> dict:
    raw = complete(system=system, user=user_message)
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def extract(text: str) -> list[dict]:
    """
    Extract atomic facts from raw text.
    Double-pass: extract then validate against original.
    Returns list of fact dicts with content, is_temporary, confidence, tags.
    """
    # Pass 1 — Extract
    try:
        data = _call_llm(EXTRACT_PROMPT, f"Extract facts from:\n\n{text}")
        facts = data.get("facts", [])
    except Exception as e:
        print(f"[Engram] Fact extraction failed: {e}")
        return [{"content": text, "is_temporary": False, "confidence": 0.7, "tags": []}]

    if not facts:
        return []

    # Pass 2 — Validate
    try:
        validation_input = f"Original text:\n{text}\n\nExtracted facts:\n{json.dumps(facts, indent=2)}"
        validated = _call_llm(VALIDATE_PROMPT, validation_input)
        facts = validated.get("facts", facts)
    except Exception as e:
        print(f"[Engram] Validation pass failed, using pass 1 results: {e}")

    return facts


def check_contradiction(new_fact: str, existing_fact: str) -> tuple[bool, str]:
    """
    Check if new_fact directly contradicts a single existing fact.
    Returns (True, reason) or (False, "").

    Checks one pair at a time so callers know exactly which memory
    to invalidate — avoids the false-positive mass-delete of the old
    batch approach.
    """
    prompt = """You are checking if two facts directly contradict each other.
A contradiction means they cannot both be true at the same time.
Semantic similarity alone is NOT a contradiction — only invalidate if
the new fact makes the existing fact factually wrong or outdated.

Examples of contradictions:
  existing: "User lives in New York"
  new:      "User lives in London"   → contradicts (location changed)

Examples that are NOT contradictions:
  existing: "User likes coffee"
  new:      "User bought a coffee machine"  → related, not contradicting
  existing: "User works at Acme"
  new:      "User's manager is Alice"       → adds detail, not contradicting

Return ONLY valid JSON, no markdown:
{"contradicts": true/false, "reason": "one sentence or empty string"}"""

    message = f"Existing fact: {existing_fact}\n\nNew fact: {new_fact}"

    try:
        data = _call_llm(prompt, message)
        return data.get("contradicts", False), data.get("reason", "")
    except Exception as e:
        print(f"[Engram] Contradiction check failed: {e}")
        return False, ""
