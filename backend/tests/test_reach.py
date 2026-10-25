from app.services.content_scoring import normalize_reach, priority_from, reach_score


def test_reach_score_log_scaled_and_bounded():
    assert reach_score(0) == 0.0
    assert reach_score(-5) == 0.0
    assert 0.0 < reach_score(1_000) < reach_score(1_000_000) <= 1.0
    assert reach_score(10_000_000) == 1.0          # caps at 10M
    assert reach_score(100_000_000) == 1.0         # stays capped


def test_priority_amplifies_risk_by_reach():
    assert priority_from(80, 0) == 80              # no reach -> priority == risk
    assert priority_from(80, 10_000_000) == 160    # max reach -> ×2
    # a viral mid-risk clip can outrank a niche high-risk one
    assert priority_from(50, 10_000_000) > priority_from(80, 0)
    assert priority_from(0, 10_000_000) == 0       # zero risk stays zero


def test_normalize_reach_coerces_safely():
    assert normalize_reach(None) == {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    assert normalize_reach({"views": "1234", "likes": None, "comments": 5}) == {
        "views": 1234, "likes": 0, "comments": 5, "shares": 0
    }
    assert normalize_reach({"views": -3})["views"] == 0      # negatives clamped
