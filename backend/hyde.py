"""
Engram — HyDE Query Expansion (Step 13)
Hypothetical Document Embeddings — generate a fake answer, search with that.
Vague queries that don't match stored memory wording.
Example:
  Raw query:   "what did we decide about APIs?"
  HyDE expands: "The team decided API responses should use camelCase format..."
  Now searches with that → finds the right memory much more reliably.
"""
import google.generativeai as genai
from config import get_settings

settings = get_settings()
genai.configure(api_key=settings.gemini_api_key)

HYDE_PROMPT = """You are helping retrieve memories from a personal AI knowledge base.

Given a search query, write a SHORT hypothetical memory (2-3 sentences) that would 
perfectly answer this query if it existed in the memory store.

Write it as if it IS a stored memory — factual, specific, past tense.
Do NOT add disclaimers or say "hypothetically". Just write the memory directly."""


def expand(query: str) -> str:
    """
    Expand a query into a hypothetical document.
    Falls back to original query if Gemini call fails.
    """
    try:
        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=HYDE_PROMPT
        )
        response = model.generate_content(f"Query: {query}")
        expanded = response.text.strip()
        print(f"[Engram] HyDE: '{query[:40]}' → '{expanded[:70]}...'")
        return expanded
    except Exception as e:
        print(f"[Engram] HyDE failed, using raw query: {e}")
        return query
