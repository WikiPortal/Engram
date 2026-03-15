"""
Engram — PII Masking Test
Run from project root: python tests/test_pii.py
"""
import sys
sys.path.append("backend")

from pii import mask, restore, has_pii


def test_pii():

    # Test 1: Detects and masks person name + email
    text = "John Smith's email is john@example.com and he leads the backend team"
    masked, token_map = mask(text)
    print(f"  Original : {text}")
    print(f"  Masked   : {masked}")
    assert "John Smith" not in masked, "Name should be masked"
    assert "john@example.com" not in masked, "Email should be masked"
    assert len(token_map) >= 1, "Should have at least 1 token"
    print(f"  ✅ Masking   — {len(token_map)} PII token(s) replaced")

    # Test 2: Restore original from token map
    restored = restore(masked, token_map)
    assert "john@example.com" in restored, "Email should be restored"
    print(f"  ✅ Restore   — original values recovered")

    # Test 3: Clean text passes through unchanged
    clean = "Team decided API responses should use camelCase"
    masked_clean, token_map_clean = mask(clean)
    assert masked_clean == clean, "Clean text should not be modified"
    assert token_map_clean == {}, "No tokens for clean text"
    print(f"  ✅ Clean text — passed through unchanged")

    # Test 4: has_pii detection
    assert has_pii("Call me at +91-9876543210") is True
    assert has_pii("We use PostgreSQL") is False
    print(f"  ✅ Detection — PII presence correctly identified")


if __name__ == "__main__":
    print("\n🧠 Engram — PII Masking Test\n")
    try:
        test_pii()
        print()
        print("✅ PII masking working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)