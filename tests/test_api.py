"""
Engram — API Test
Run from project root: python tests/test_api.py

Requires:
  - Docker running
  - API server running: cd backend && uvicorn api:app --port 8000

Tests all 6 endpoints against the live server.
"""
import sys
import uuid
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
USER = "test_api_" + uuid.uuid4().hex[:8]


def request(method: str, path: str, body: dict = None) -> tuple[int, dict]:
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health():
    print("  GET /health ...")
    status, body = request("GET", "/health")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body["status"] == "ok"
    print(f"  ✅ /health ok — graph nodes: {body['graph']['nodes']}")


def test_store():
    print("\n  POST /memory/store ...")
    status, body = request("POST", "/memory/store", {
        "content": "Team decided the API uses camelCase. John leads backend. Deadline is next Friday.",
        "user_id": USER,
        "tags": ["api", "team"]
    })
    assert status == 201, f"Expected 201, got {status}: {body}"
    assert body["stored"] > 0, f"Should store at least 1 fact: {body}"
    print(f"  ✅ /memory/store — stored: {body['stored']}, graph_edges: {body['graph_edges']}")
    for f in body["facts"]:
        print(f"    → {f[:70]}")


def test_recall():
    print("\n  POST /memory/recall ...")
    status, body = request("POST", "/memory/recall", {
        "query": "what naming convention do we use for the API?",
        "user_id": USER
    })
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert len(body["memories"]) > 0, "Should return at least 1 memory"
    top = body["memories"][0]
    print(f"  ✅ /memory/recall — found: {body['total_found']}, tokens: {body['context_tokens']}")
    print(f"    Top result: {top['content'][:70]}")


def test_list():
    print("\n  GET /memory/list/{user_id} ...")
    status, body = request("GET", f"/memory/list/{USER}")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert len(body) > 0, "Should return stored memories"
    print(f"  ✅ /memory/list — returned {len(body)} memories")
    print(f"    First: {body[0]['content'][:60]}")


def test_delete():
    print("\n  DELETE /memory/{memory_id} ...")
    # Get a memory ID to delete
    _, memories = request("GET", f"/memory/list/{USER}")
    assert memories, "Need at least one memory to delete"
    target_id = memories[0]["id"]

    status, body = request("DELETE", f"/memory/{target_id}")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body["status"] == "invalidated"
    print(f"  ✅ /memory/delete — invalidated {target_id[:12]}...")

    # Verify it's gone from the list
    _, after = request("GET", f"/memory/list/{USER}")
    ids_after = {m["id"] for m in after}
    assert target_id not in ids_after, "Deleted memory should not appear in list"
    print(f"  ✅ Confirmed removed from list")


def test_chat():
    print("\n  POST /chat ...")
    status, body = request("POST", "/chat", {
        "message": "What naming convention did we decide on for the API?",
        "user_id": USER
    })
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert len(body["response"]) > 0
    assert "camel" in body["response"].lower() or "camelcase" in body["response"].lower(), \
        f"Response should mention camelCase, got: {body['response']}"
    print(f"  ✅ /chat — memories_used: {body['memories_used']}")
    print(f"    Response: {body['response'][:120]}")


def test_validation():
    print("\n  Input validation ...")
    # Empty content should 400
    status, _ = request("POST", "/memory/store", {"content": "  ", "user_id": USER})
    assert status == 400, f"Empty content should return 400, got {status}"

    # Empty query should 400
    status, _ = request("POST", "/memory/recall", {"query": "", "user_id": USER})
    assert status == 400, f"Empty query should return 400, got {status}"
    print("  ✅ Validation working")


if __name__ == "__main__":
    print("\n🧠 Engram — API Test\n")
    print(f"  Target: {BASE}\n")

    # Quick connectivity check
    try:
        request("GET", "/health")
    except Exception:
        print(f"❌ Cannot reach {BASE}")
        print("   Make sure the server is running:")
        print("   cd backend && uvicorn api:app --port 8000")
        sys.exit(1)

    try:
        test_health()
        test_store()
        test_recall()
        test_list()
        test_delete()
        test_chat()
        test_validation()
        print()
        print("✅ All API endpoints working.\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
