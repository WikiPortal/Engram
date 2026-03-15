"""
Engram — Brain (Step 14)
Full pipeline wiring all components together.

STORE pipeline:
  input → PII mask → extract facts → dedup check → contradiction check
        → TTL classify → store in Qdrant

RECALL pipeline:
  query → HyDE expand → hybrid search → TTL filter → rerank → context guard → return
"""
import tiktoken
import pii
from extractor import extract
from dedup import is_duplicate
from contradiction import resolve
from ttl import get_expiry, set_ttl, is_expired
from memory import store as _store_raw, recall as _recall_raw
from search import hybrid_search
from reranker import rerank
from hyde import expand
from config import get_settings

settings = get_settings()

tokenizer = tiktoken.get_encoding("cl100k_base")


# ── STORE ────────────────────────────────────────────────────────

def remember(content: str, user_id: str = "default", tags: list[str] = []) -> dict:
    """
    Full store pipeline.
    Returns summary of what was stored.
    """
    result = {
        "stored": 0,
        "skipped_duplicates": 0,
        "contradictions_resolved": 0,
        "facts": []
    }

    # Step 1 — PII masking
    masked, token_map = pii.mask(content)

    # Step 2 — Extract facts (double-pass Gemini)
    facts = extract(masked)
    if not facts:
        # Fallback: store raw as single fact
        facts = [{"content": masked, "is_temporary": None, "confidence": 0.7, "tags": tags}]

    # Step 3 — Process each fact
    for fact in facts:
        fact_content = fact.get("content", "").strip()
        if not fact_content:
            continue

        fact_tags = list(set(tags + fact.get("tags", [])))

        # Step 4 — Duplicate check
        dup, match, score = is_duplicate(fact_content, user_id)
        if dup:
            print(f"[Engram] Skipping duplicate (score {score}): {fact_content[:50]}")
            result["skipped_duplicates"] += 1
            continue

        # Step 5 — Contradiction resolution
        found, invalidated = resolve(fact_content, user_id)
        if found:
            result["contradictions_resolved"] += len(invalidated)

        # Step 6 — Store in Qdrant
        memory_id = _store_raw(fact_content, user_id=user_id, tags=fact_tags)

        # Step 7 — TTL classification
        expires_at = get_expiry(
            fact_content,
            is_temporary_hint=fact.get("is_temporary")
        )
        if expires_at:
            set_ttl(memory_id, expires_at)

        result["stored"] += 1
        result["facts"].append(fact_content)

    return result


# ── RECALL ───────────────────────────────────────────────────────

def recall(query: str, user_id: str = "default") -> dict:
    """
    Full recall pipeline.
    Returns top memories with context token count.
    """

    # Step 1 — HyDE expansion
    expanded_query = expand(query)

    # Step 2 — Hybrid search (BM25 + vector + RRF)
    candidates = hybrid_search(expanded_query, user_id=user_id, top_k=settings.top_k_retrieval)

    if not candidates:
        return {"query": query, "memories": [], "total_found": 0, "context_tokens": 0}

    # Step 3 — Filter expired TTL memories
    active = [c for c in candidates if not is_expired(c["id"])]

    # Step 4 — BGE rerank
    reranked = rerank(query, active, top_k=settings.top_k_reranked)

    # Step 5 — Context window guard (max 2000 tokens)
    final = []
    total_tokens = 0
    for memory in reranked:
        tokens = len(tokenizer.encode(memory["content"]))
        if total_tokens + tokens > settings.max_context_tokens:
            print(f"[Engram] Context cap reached at {total_tokens} tokens")
            break
        final.append(memory)
        total_tokens += tokens

    return {
        "query": query,
        "memories": final,
        "total_found": len(candidates),
        "context_tokens": total_tokens
    }


# ── CHAT ─────────────────────────────────────────────────────────

def chat(message: str, user_id: str = "default", history: list[dict] = []) -> str:
    """
    Memory-augmented chat.
    Recalls relevant memories → injects into Gemini prompt → returns answer.
    """
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)

    # Recall relevant memories
    result = recall(message, user_id=user_id)
    memories = result["memories"]

    # Build memory context string
    if memories:
        memory_context = "Relevant memories from your knowledge base:\n"
        for i, m in enumerate(memories, 1):
            memory_context += f"{i}. {m['content']}\n"
        memory_context += "\n"
    else:
        memory_context = ""

    system_prompt = f"""You are a personal AI assistant with access to the user's memory bank.
{memory_context}Use the memories above as context when answering. 
If memories are not relevant, answer from general knowledge.
Be concise and helpful."""

    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system_prompt
    )

    # Build conversation history
    gemini_history = []
    for msg in history:
        gemini_history.append({
            "role": msg["role"],
            "parts": [msg["content"]]
        })

    chat_session = model.start_chat(history=gemini_history)
    response = chat_session.send_message(message)
    return response.text
