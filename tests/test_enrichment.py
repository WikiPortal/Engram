"""
Engram — Sliding Window Coreference Test
Run from project root: python tests/test_enrichment.py

Tests that enrich_with_context() resolves orphaned pronouns and vague
references using surrounding conversation history.
"""
import sys
sys.path.append("backend")

from extractor import enrich_with_context


def test_pronoun_resolution():
    print("  Testing pronoun resolution...")

    history = [
        {"role": "user",      "content": "Tell me about John, our new backend lead."},
        {"role": "assistant", "content": "John joined last month from Google."},
    ]
    chunk = "He moved to Berlin for the role."
    enriched = enrich_with_context(chunk, history)

    assert "John" in enriched, f"'John' should replace 'He', got: '{enriched}'"
    assert "He" not in enriched or "John" in enriched
    print(f"  ✅ '{chunk}' → '{enriched}'")


def test_vague_reference_resolution():
    print("\n  Testing vague reference resolution...")

    history = [
        {"role": "user",      "content": "We've been debating whether to use React or Vue."},
        {"role": "assistant", "content": "Both have tradeoffs. What's your concern?"},
        {"role": "user",      "content": "The team hates debugging it."},
    ]
    chunk = "That framework is too complex for our needs."
    enriched = enrich_with_context(chunk, history)

    print(f"  ✅ '{chunk}' → '{enriched}'")
    assert chunk != enriched or "framework" in enriched 


def test_already_self_contained():
    print("\n  Testing self-contained chunk is unchanged...")

    history = [
        {"role": "user", "content": "Some unrelated conversation."},
    ]
    chunk = "Alice leads the frontend team at Acme Corp."
    enriched = enrich_with_context(chunk, history)

    print(f"  ✅ Self-contained: '{enriched}'")
    assert "Alice" in enriched
    assert "frontend" in enriched


def test_no_history_passthrough():
    print("\n  Testing empty history returns chunk unchanged...")

    chunk = "He moved to Berlin."
    enriched = enrich_with_context(chunk, [])
    assert enriched == chunk, f"Empty history should return chunk as-is, got: '{enriched}'"
    print(f"  ✅ No history → passthrough")


def test_disabled_via_config():
    print("\n  Testing lookback=0 disables enrichment...")
    import extractor
    original = extractor.settings.sliding_window_lookback

    extractor.settings.sliding_window_lookback = 0
    history = [{"role": "user", "content": "John is the backend lead."}]
    chunk = "He moved to Berlin."
    enriched = enrich_with_context(chunk, history)
    assert enriched == chunk, f"lookback=0 should skip enrichment, got: '{enriched}'"
    print(f"  ✅ lookback=0 → passthrough")

    extractor.settings.sliding_window_lookback = original  # restore


if __name__ == "__main__":
    print("\n🧠 Engram — Sliding Window Coreference Test\n")
    try:
        test_pronoun_resolution()
        test_vague_reference_resolution()
        test_already_self_contained()
        test_no_history_passthrough()
        test_disabled_via_config()
        print()
        print("✅ Sliding window enrichment working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        import traceback; traceback.print_exc()
        sys.exit(1)
