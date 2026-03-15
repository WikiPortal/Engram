"""
Engram — TTL / Auto-Forget Test
Run from project root: python tests/test_ttl.py
"""
import sys
import time
sys.path.append("backend")

from ttl import get_expiry, set_ttl, is_expired, get_ttl_seconds
import uuid


def test_classification():
    print("  Testing TTL classification...")

    # Should be temporary
    temp_cases = [
        "Meeting with John tomorrow at 3pm",
        "Deadline is next Friday",
        "Call the client today",
        "Reminder to send the report this week",
    ]
    for text in temp_cases:
        expiry = get_expiry(text)
        assert expiry is not None, f"Should be temporary: '{text}'"
        print(f"  ⏰ '{text[:45]}' → expires {expiry.strftime('%Y-%m-%d')}")

    # Should be permanent
    perm_cases = [
        "Team agreed API should always use camelCase",
        "Company policy is remote-first",
        "John leads the backend team",
    ]
    for text in perm_cases:
        expiry = get_expiry(text)
        assert expiry is None, f"Should be permanent: '{text}'"
        print(f"  📌 '{text[:45]}' → permanent")

    print("  ✅ Classification correct")


def test_redis_ttl():
    print("\n  Testing Redis TTL set + expiry...")
    memory_id = str(uuid.uuid4())

    from datetime import datetime, timedelta, timezone
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=3)
    set_ttl(memory_id, expires_at)

    remaining = get_ttl_seconds(memory_id)
    assert remaining is not None and remaining > 0, "Should have TTL set"
    assert not is_expired(memory_id), "Should not be expired yet"
    print(f"  ✅ TTL set — {remaining}s remaining")

    print("  Waiting 4 seconds for expiry...")
    time.sleep(4)

    assert is_expired(memory_id), "Should be expired after 4 seconds"
    print("  ✅ Memory auto-expired from Redis")


def test_hint_override():
    print("\n  Testing extractor hint override...")
    # Extractor says temporary → should set TTL even without time words
    expiry = get_expiry("John is out of office", is_temporary_hint=True)
    assert expiry is not None, "Hint=True should force temporary"
    print("  ✅ Hint=True forces expiry")

    # Extractor says permanent → should override time words
    expiry = get_expiry("We always have meetings on Monday", is_temporary_hint=False)
    assert expiry is None, "Hint=False should force permanent"
    print("  ✅ Hint=False forces permanent")


if __name__ == "__main__":
    print("\n🧠 Engram — TTL / Auto-Forget Test\n")
    try:
        test_classification()
        test_redis_ttl()
        test_hint_override()
        print()
        print("✅ TTL working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
