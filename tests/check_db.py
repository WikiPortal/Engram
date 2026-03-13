"""
Engram — Database Health Check
Run from project root: python tests/check_db.py
Usage: python scripts/check_db.py
"""
import sys

def check_qdrant():
    try:
        import httpx
        r = httpx.get("http://localhost:6333/healthz", timeout=3)
        assert r.status_code == 200
        print("  ✅ Qdrant      — running on :6333")
    except Exception as e:
        print(f"  ❌ Qdrant      — FAILED ({e})")
        return False
    return True

def check_postgres():
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=5432,
            dbname="engram", user="engram", password="engram_secret",
            connect_timeout=3
        )
        conn.close()
        print("  ✅ PostgreSQL  — running on :5432")
    except Exception as e:
        print(f"  ❌ PostgreSQL  — FAILED ({e})")
        return False
    return True

def check_redis():
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_timeout=3)
        r.ping()
        print("  ✅ Redis       — running on :6379")
    except Exception as e:
        print(f"  ❌ Redis       — FAILED ({e})")
        return False
    return True

def check_falkordb():
    try:
        import redis
        r = redis.Redis(host="localhost", port=6380, socket_timeout=3)
        r.ping()
        print("  ✅ FalkorDB    — running on :6380")
    except Exception as e:
        print(f"  ❌ FalkorDB    — FAILED ({e})")
        return False
    return True

if __name__ == "__main__":
    print("\n🧠 Engram — Database Health Check\n")
    results = [
        check_qdrant(),
        check_postgres(),
        check_redis(),
        check_falkordb(),
    ]
    print()
    if all(results):
        print("✅ All databases running.\n")
    else:
        print("❌ Some databases failed. Run: docker compose up -d\n")
        sys.exit(1)