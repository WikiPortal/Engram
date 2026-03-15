"""
Engram — Fact Extractor
Uses Gemini to extract clean atomic facts from raw input.
"""
import json
import google.generativeai as genai
from config import get_settings

settings = get_settings()
genai.configure(api_key=settings.gemini_api_key)


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


def _call_gemini(prompt: str, user_message: str) -> dict:
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=prompt
    )
    response = model.generate_content(user_message)
    raw = response.text.strip()
    # Strip markdown fences if Gemini adds them
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
        data = _call_gemini(EXTRACT_PROMPT, f"Extract facts from:\n\n{text}")
        facts = data.get("facts", [])
    except Exception as e:
        print(f"[Engram] Fact extraction failed: {e}")
        # Fallback: treat entire input as one fact
        return [{"content": text, "is_temporary": False, "confidence": 0.7, "tags": []}]

    if not facts:
        return []

    # Pass 2 — Validate (catches negation errors ~2-3% of the time)
    try:
        validation_input = f"Original text:\n{text}\n\nExtracted facts:\n{json.dumps(facts, indent=2)}"
        validated = _call_gemini(VALIDATE_PROMPT, validation_input)
        facts = validated.get("facts", facts)  # fallback to pass 1 if validation fails
    except Exception as e:
        print(f"[Engram] Validation pass failed, using pass 1 results: {e}")

    return facts


def is_contradiction(new_fact: str, existing_facts: list[str]) -> tuple[bool, str]:
    """
    Check if new_fact contradicts any existing facts.
    Returns (True, reason) or (False, "")
    """
    if not existing_facts:
        return False, ""

    prompt = """You are checking if a new fact contradicts existing stored facts.
Return ONLY valid JSON:
{"contradicts": true/false, "reason": "brief explanation or empty string"}"""

    existing_str = "\n".join(f"- {f}" for f in existing_facts)
    message = f"New fact: {new_fact}\n\nExisting facts:\n{existing_str}"

    try:
        data = _call_gemini(prompt, message)
        return data.get("contradicts", False), data.get("reason", "")
    except Exception as e:
        print(f"[Engram] Contradiction check failed: {e}")
        return False, ""