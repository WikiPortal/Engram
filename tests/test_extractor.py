"""
Engram — Fact Extractor Test
Run from project root: python tests/test_extractor.py
"""
import sys
sys.path.append("backend")

from extractor import extract, check_contradiction


def test_extraction():
    print("  Testing basic extraction...")
    facts = extract("Had a team meeting today. John will lead the backend. We agreed the API should use camelCase. Deadline is next Friday.")
    assert len(facts) > 0, "Should extract at least 1 fact"
    print(f"  ✅ Extracted {len(facts)} facts:")
    for f in facts:
        temp = "⏰" if f["is_temporary"] else "📌"
        print(f"     {temp} [{f['confidence']:.2f}] {f['content']}")


def test_negation():
    print("\n  Testing negation handling (critical edge case)...")
    facts = extract("I don't like using MongoDB. We should not use camelCase for database fields.")
    assert len(facts) > 0
    contents = [f["content"].lower() for f in facts]
    # Make sure negation is preserved — "dislikes" or "not" should appear
    negation_preserved = any("not" in c or "dislike" in c or "avoid" in c or "should not" in c for c in contents)
    assert negation_preserved, f"Negation not preserved in: {contents}"
    print(f"  ✅ Negation preserved correctly")
    for f in facts:
        print(f"     📌 {f['content']}")


def test_contradiction():
    print("\n  Testing contradiction detection (per-fact, not batch)...")

    # Case 1: direct contradiction — new fact supersedes existing
    is_contra, reason = check_contradiction(
        "Sarah now leads the backend team",
        "John leads the backend team"
    )
    assert is_contra, "Should detect contradiction: leadership changed"
    print(f"  ✅ Contradiction detected: {reason}")

    # Case 2: semantically related but NOT contradicting
    is_contra2, _ = check_contradiction(
        "We deployed on Friday",
        "John leads the backend team"
    )
    assert not is_contra2, "Should NOT flag unrelated fact as contradiction"
    print(f"  ✅ Unrelated fact correctly ignored")

    # Case 3: additive detail — must NOT be flagged as contradiction
    is_contra3, _ = check_contradiction(
        "User bought a coffee machine",
        "User likes coffee"
    )
    assert not is_contra3, "Adding detail should NOT contradict the original"
    print(f"  ✅ Additive detail correctly ignored")


if __name__ == "__main__":
    print("\n🧠 Engram — Fact Extractor Test\n")
    try:
        test_extraction()
        test_negation()
        test_contradiction()
        print()
        print("✅ Fact extractor working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)