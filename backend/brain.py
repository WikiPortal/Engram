"""
Engram — Brain (Step 14)
Full pipeline wiring all components together.

STORE pipeline:
  input → PII mask → extract facts → dedup check → contradiction check
        → TTL classify → store in Qdrant → graph link (FalkorDB)

RECALL pipeline:
  query → HyDE expand → hybrid search → TTL filter → graph expand
        → rerank → context guard → return
"""
import tiktoken
import pii
from db import get_qdrant
from embedder import embedder as _embedder
from qdrant_client.models import Filter, FieldCondition, MatchValue
from extractor import extract
from dedup import is_duplicate
from contradiction import resolve, invalidate_memory
from ttl import get_expiry, set_ttl, is_expired
from memory import store as _store_raw, recall as _recall_raw
from search import hybrid_search
from reranker import rerank
from hyde import expand
from graph import link_memories, get_related, invalidate_edges
from llm import chat_complete
from config import get_settings

settings = get_settings()

tokenizer = tiktoken.get_encoding("cl100k_base")


def remember(content: str, user_id: str = "default", tags: list[str] = []) -> dict:
    """
    Full store pipeline.
    Returns summary of what was stored.
    """
    result = {
        "stored": 0,
        "skipped_duplicates": 0,
        "contradictions_resolved": 0,
        "graph_edges": 0,
        "facts": []
    }

    masked, token_map = pii.mask(content)

    facts = extract(masked)
    if not facts:
        facts = [{"content": masked, "is_temporary": None, "confidence": 0.7, "tags": tags}]

    for fact in facts:
        fact_content = fact.get("content", "").strip()
        if not fact_content:
            continue

        fact_tags = list(set(tags + fact.get("tags", [])))

        dup, match, score = is_duplicate(fact_content, user_id)
        if dup:
            print(f"[Engram] Skipping duplicate (score {score}): {fact_content[:50]}")
            result["skipped_duplicates"] += 1
            continue

        found, invalidated = resolve(fact_content, user_id)
        if found:
            result["contradictions_resolved"] += len(invalidated)
            for inv_id in invalidated:
                invalidate_edges(inv_id)

        memory_id = _store_raw(fact_content, user_id=user_id, tags=fact_tags)

        expires_at = get_expiry(
            fact_content,
            is_temporary_hint=fact.get("is_temporary")
        )
        if expires_at:
            set_ttl(memory_id, expires_at)

        try:
            client = get_qdrant()
            vec = _embedder.embed(fact_content)
            nearby = client.search(
                collection_name=settings.qdrant_collection,
                query_vector=vec,
                query_filter=Filter(must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="is_latest", match=MatchValue(value=True)),
                    FieldCondition(key="is_valid",  match=MatchValue(value=True)),
                ]),
                limit=5,
                with_payload=True,
            )
            candidates_for_graph = [
                {"id": str(r.id), "content": r.payload["content"], "score": r.score}
                for r in nearby
                if str(r.id) != memory_id and r.score > 0.4
            ]
            edges = link_memories(memory_id, fact_content, candidates_for_graph, user_id)
            result["graph_edges"] += len(edges)
        except Exception as e:
            print(f"[Engram] Graph linking failed (non-critical): {e}")

        result["stored"] += 1
        result["facts"].append(fact_content)

    return result


def recall(query: str, user_id: str = "default") -> dict:
    """
    Full recall pipeline.
    Returns top memories with context token count.
    """

    expanded_query = expand(query)

    candidates = hybrid_search(expanded_query, user_id=user_id, top_k=settings.top_k_retrieval)

    if not candidates:
        return {"query": query, "memories": [], "total_found": 0, "context_tokens": 0}

    active = [c for c in candidates if not is_expired(c["id"])]

    try:
        client = get_qdrant()
        seen_ids = {c["id"] for c in active}
        graph_additions = []

        for candidate in active[:5]:  # bound latency — only expand top 5
            related = get_related(candidate["id"], user_id=user_id, depth=1)
            for rel in related:
                if rel["id"] not in seen_ids:
                    hits = client.retrieve(
                        collection_name=settings.qdrant_collection,
                        ids=[rel["id"]],
                        with_payload=True,
                    )
                    if hits and hits[0].payload.get("is_valid") and hits[0].payload.get("is_latest"):
                        graph_additions.append({
                            "id":         rel["id"],
                            "content":    hits[0].payload["content"],
                            "tags":       hits[0].payload.get("tags", []),
                            "created_at": hits[0].payload.get("created_at", ""),
                            "graph_rel":  rel["rel_type"],
                        })
                        seen_ids.add(rel["id"])

        if graph_additions:
            print(f"[Engram] Graph expansion added {len(graph_additions)} neighbour(s)")
            active = active + graph_additions
    except Exception as e:
        print(f"[Engram] Graph expansion failed (non-critical): {e}")

    reranked = rerank(query, active, top_k=settings.top_k_reranked)

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
        "query":          query,
        "memories":       final,
        "total_found":    len(candidates),
        "context_tokens": total_tokens,
    }


# ── CHAT ─────────────────────────────────────────────────────────

def chat(message: str, user_id: str = "default", history: list[dict] = []) -> str:
    """
    Memory-augmented chat.
    Recalls relevant memories → injects into system prompt → returns answer.
    Works with any configured LLM provider (Gemini, OpenAI, Anthropic, DeepSeek).
    """

    result = recall(message, user_id=user_id)
    memories = result["memories"]

    if memories:
        memory_context = "Relevant memories from your knowledge base:\n"
        for i, m in enumerate(memories, 1):
            memory_context += f"{i}. {m['content']}\n"
        memory_context += "\n"
    else:
        memory_context = ""

    system_prompt = (
        "You are a personal AI assistant with access to the user's memory bank.\n"
        f"{memory_context}"
        "Use the memories above as context when answering. "
        "If memories are not relevant, answer from general knowledge. "
        "Be concise and helpful."
    )

    return chat_complete(system=system_prompt, history=history, message=message)
