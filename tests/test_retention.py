"""
Engram — Bio-Mimetic Retention Scoring Test
Run from project root: python tests/test_retention.py
"""
import sys
import math
sys.path.append("backend")

from config import get_settings
get_settings.cache_clear()

from retention import (
    init_retention, compute_score, record_access,
    filter_by_retention, is_forgotten,
    _salience_high, _salience_low, _access_boost, _forget_threshold,
)
import retention as _ret
import uuid


def _mid():
    return str(uuid.uuid4())


def test_salience_classification():
    print("  Testing salience classification...")

    high_cases = [
        "User is allergic to penicillin",
        "User's name is Alice",
        "User works at Google",
        "User lives in Berlin",
        "User was born in 1990",
    ]
    low_cases = [
        "User prefers tabs over spaces",
        "Team uses Slack for communication",
        "The deployment runs on Fridays",
    ]

    for content in high_cases:
        mid = _mid()
        init_retention(mid, content)
        score = compute_score(mid)
        assert score >= 0.9, f"High-salience should start near 1.0, got {score}: '{content}'"
        print(f"  ✅ High [{score:.3f}]: '{content[:50]}'")

    for content in low_cases:
        mid = _mid()
        init_retention(mid, content)
        score = compute_score(mid)
        assert score >= 0.4, f"Low-salience should start ~0.5, got {score}: '{content}'"
        print(f"  ✓  Low  [{score:.3f}]: '{content[:50]}'")


def test_fresh_memory_score():
    print("\n  Testing fresh memory has high score...")
    mid = _mid()
    init_retention(mid, "User graduated from MIT with a CS degree")
    score = compute_score(mid)
    assert score >= 0.9, f"Fresh high-salience memory should score near 1.0, got {score}"
    print(f"  ✅ Fresh memory score: {score:.4f}")


def test_access_boosts_score():
    print("\n  Testing that accessing a memory boosts its retention score...")
    mid = _mid()
    # Low-salience content → salience=0.5 → score clearly below 1.0
    init_retention(mid, "User prefers tabs over spaces")

    score_before = compute_score(mid)
    print(f"     Score before accesses: {score_before:.4f}")
    assert score_before < 1.0, f"Low-salience fresh memory should score 0.5, got {score_before}"

    record_access(mid)
    record_access(mid)
    record_access(mid)
    score_after = compute_score(mid)
    print(f"     Score after 3 accesses: {score_after:.4f}")

    assert score_after > score_before, (
        f"Score should increase after accesses.\n"
        f"  Before: {score_before:.4f}, After: {score_after:.4f}\n"
        f"  access_boost setting: {_access_boost()}"
    )
    print(f"  ✅ Score increased by {score_after - score_before:.4f} after 3 accesses")


def test_filter_disabled_by_default():
    print("\n  Testing filter is disabled by default (threshold=0)...")

    memories = [
        {"id": _mid(), "content": "Fact A"},
        {"id": _mid(), "content": "Fact B"},
    ]
    for m in memories:
        init_retention(m["id"], m["content"])

    # Monkeypatch _forget_threshold to return 0.0
    orig = _ret._forget_threshold
    _ret._forget_threshold = lambda: 0.0

    filtered = filter_by_retention(memories)
    _ret._forget_threshold = orig

    assert len(filtered) == len(memories), \
        f"With threshold=0, no memories should be filtered. Got {len(filtered)}/{len(memories)}"
    print(f"  ✅ All {len(memories)} memories passed (threshold disabled)")


def test_filter_removes_forgotten():
    print("\n  Testing filter removes memories below threshold...")

    mid = _mid()
    init_retention(mid, "Some trivial fact with low salience score")
    score = compute_score(mid)

    # Monkeypatch threshold to just above current score
    threshold = score + 0.01
    orig = _ret._forget_threshold
    _ret._forget_threshold = lambda: threshold

    memories = [{"id": mid, "content": "Some trivial fact"}]
    filtered = filter_by_retention(memories)

    _ret._forget_threshold = orig

    assert len(filtered) == 0, \
        f"Memory with score {score:.4f} should be filtered at threshold {threshold:.4f}"
    print(f"  ✅ Memory with score {score:.4f} correctly filtered at threshold {threshold:.4f}")


def test_missing_metadata_safe():
    print("\n  Testing missing metadata returns safe default (1.0)...")
    fake_id = "nonexistent-" + _mid()
    score = compute_score(fake_id)
    assert score == 1.0, f"Missing metadata should return 1.0, got {score}"
    assert not is_forgotten(fake_id), "Missing metadata should never trigger forgotten"
    print(f"  ✅ Missing metadata → score={score} (safe default)")


if __name__ == "__main__":
    print("\n🧠 Engram — Retention Scoring Test\n")
    try:
        test_salience_classification()
        test_fresh_memory_score()
        test_access_boosts_score()
        test_filter_disabled_by_default()
        test_filter_removes_forgotten()
        test_missing_metadata_safe()
        print()
        print("✅ Retention scoring working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        import traceback; traceback.print_exc()
        sys.exit(1)
