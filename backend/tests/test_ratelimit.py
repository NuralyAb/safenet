from app.core.ratelimit import RateLimiter


def test_allows_up_to_max_then_blocks():
    rl = RateLimiter(max_attempts=3, window_seconds=60)
    assert [rl.allow("ip", now=0) for _ in range(3)] == [True, True, True]
    assert rl.allow("ip", now=1) is False        # 4th within window


def test_window_slides_and_frees_capacity():
    rl = RateLimiter(max_attempts=2, window_seconds=10)
    assert rl.allow("ip", now=0) is True
    assert rl.allow("ip", now=5) is True
    assert rl.allow("ip", now=6) is False        # full
    assert rl.allow("ip", now=11) is True        # first hit (t=0) aged out


def test_keys_are_independent():
    rl = RateLimiter(max_attempts=1, window_seconds=60)
    assert rl.allow("a", now=0) is True
    assert rl.allow("b", now=0) is True          # different client unaffected
    assert rl.allow("a", now=0) is False
