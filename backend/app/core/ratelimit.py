"""In-memory login-failure throttle (per client + email). Single-process only; swap for Redis when scaling out."""
import time
from collections import defaultdict, deque


class FailureLimiter:
    def __init__(self, max_failures: int = 5, window_seconds: int = 900, clock=time.monotonic):
        self.max_failures, self.window, self.clock = max_failures, window_seconds, clock
        self._fails: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str) -> deque:
        q = self._fails[key]
        cutoff = self.clock() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until another attempt is allowed; 0 when the key is not blocked."""
        q = self._prune(key)
        if len(q) < self.max_failures:
            return 0
        return max(1, int(q[0] + self.window - self.clock()) + 1)

    def record_failure(self, key: str) -> None:
        self._prune(key).append(self.clock())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


login_limiter = FailureLimiter()
