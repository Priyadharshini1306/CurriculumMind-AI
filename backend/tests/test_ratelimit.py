from app.core.ratelimit import FailureLimiter


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_blocks_after_max_failures_then_recovers():
    clk = Clock()
    lim = FailureLimiter(max_failures=3, window_seconds=60, clock=clk)
    for _ in range(2):
        lim.record_failure("k")
    assert lim.retry_after("k") == 0
    lim.record_failure("k")
    assert 0 < lim.retry_after("k") <= 61
    clk.t += 61
    assert lim.retry_after("k") == 0  # window passed


def test_keys_are_independent_and_reset_clears():
    lim = FailureLimiter(max_failures=1, window_seconds=60, clock=Clock())
    lim.record_failure("a")
    assert lim.retry_after("a") > 0 and lim.retry_after("b") == 0
    lim.reset("a")
    assert lim.retry_after("a") == 0
