"""
Engram — Fact Extractor
Uses the configured LLM provider to extract clean atomic facts from raw input.
"""
import json
from llm import complete
from config import get_settings

settings = get_settings()

ENRICH_PROMPT = """You are a context enrichment engine for a personal AI memory system.

Your job: make a chunk of text fully self-contained by resolving any vague
references using the surrounding conversation context provided.

Rules:
1. Replace pronouns (he/she/they/it/his/her/their) with the explicit entity
   name when it can be determined from context.
   Example: context says "talking about John" + chunk "He moved to Berlin"
            → enriched: "John moved to Berlin"

2. Replace vague noun phrases with their referent when determinable.
   Example: context "discussing the React project" + chunk "that framework is slow"
            → enriched: "React is slow"
   Example: context "user works at Acme Corp" + chunk "the company pivoted"
            → enriched: "Acme Corp pivoted"

3. If a reference CANNOT be resolved from context, leave the original wording.
   Never guess or hallucinate an entity.

4. Do NOT add new information. Do NOT summarise. Do NOT change meaning.
   Only substitute ambiguous references with explicit names.

5. If the chunk is already fully self-contained, return it unchanged.

Return ONLY the enriched text — no explanation, no JSON, no markdown."""


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


def enrich_with_context(chunk: str, history: list[dict]) -> str:
    """
    Sliding Window Coreference Resolution.

    Resolves pronouns and vague references in `chunk` using the last
    N turns in `history` as context, producing a self-contained chunk
    that can be fact-extracted without losing entity identity.

    This directly addresses HydraDB's finding that ~40% of naively
    chunked text becomes semantically invisible because "he/she/it/that
    framework" have no referent in the isolated chunk.

    Args:
        chunk:   The raw text to enrich (single turn or message).
        history: List of prior turns as {"role": "user"|"assistant",
                 "content": "..."} dicts, most recent last.
                 Only the last `settings.sliding_window_lookback` turns
                 are used.

    Returns:
        Enriched text with resolved references. Falls back to the
        original `chunk` if the LLM call fails or enrichment is
        disabled (sliding_window_lookback == 0).
    """
    lookback = settings.sliding_window_lookback

    if lookback == 0 or not history:
        return chunk

    window = history[-lookback:]

    context_lines = []
    for turn in window:
        role    = turn.get("role", "user").capitalize()
        content = turn.get("content", "").strip()
        if content:
            context_lines.append(f"{role}: {content}")

    if not context_lines:
        return chunk

    context_str = "\n".join(context_lines)
    user_message = (
        f"Conversation context (most recent last):\n"
        f"{context_str}\n\n"
        f"Chunk to enrich:\n{chunk}"
    )

    try:
        enriched = complete(system=ENRICH_PROMPT, user=user_message).strip()
        if enriched and enriched != chunk:
            print(f"[Engram:Enrich] '{chunk[:50]}' → '{enriched[:50]}'")
        return enriched if enriched else chunk
    except Exception as e:
        print(f"[Engram:Enrich] Failed (using raw chunk): {e}")
        return chunk


def extract(text: str, history: list[dict] | None = None) -> list[dict]:
    """
    Extract atomic facts from raw text.

    If `history` is provided, runs sliding window coreference resolution
    first to make `text` self-contained before extraction.

    Double-pass: extract then validate against the enriched text.
    Returns list of fact dicts with content, is_temporary, confidence, tags.
    """

    enriched_text = enrich_with_context(text, history or [])

    # Pass 1 — Extract
    try:
        data = _call_llm(EXTRACT_PROMPT, f"Extract facts from:\n\n{enriched_text}")
        facts = data.get("facts", [])
    except Exception as e:
        print(f"[Engram] Fact extraction failed: {e}")
        return [{"content": enriched_text, "is_temporary": False, "confidence": 0.7, "tags": []}]

    if not facts:
        return []

    try:
        validation_input = (
            f"Original text:\n{enriched_text}\n\n"
            f"Extracted facts:\n{json.dumps(facts, indent=2)}"
        )
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
