"""
Engram — HyDE Query Expansion
Hypothetical Document Embeddings — generate a fake answer, search with that.
"""
from llm import complete
from config import get_settings

settings = get_settings()

HYDE_PROMPT = """You are helping retrieve memories from a personal AI knowledge base.

Given a search query, write a SHORT hypothetical memory (2-3 sentences) that would 
perfectly answer this query if it existed in the memory store.

Write it as if it IS a stored memory — factual, specific, past tense.
Do NOT add disclaimers or say "hypothetically". Just write the memory directly."""


def expand(query: str) -> str:
    """
    Expand a query into a hypothetical document.
    Falls back to original query if LLM call fails.
    """
    try:
        expanded = complete(system=HYDE_PROMPT, user=f"Query: {query}")
        print(f"[Engram] HyDE: '{query[:40]}' → '{expanded[:70]}...'")
        return expanded
    except Exception as e:
        print(f"[Engram] HyDE failed, using raw query: {e}")
        return query
