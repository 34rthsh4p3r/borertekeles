from collections import deque
from hashlib import blake2b
from secrets import token_bytes
from threading import Lock
from time import monotonic


class RateLimiter:
    """Process-local sliding window. Only short-lived, keyed IP digests are kept."""

    def __init__(self, per_address: int, total: int, window: float = 60):
        self.per_address = per_address
        self.total = total
        self.window = window
        self.salt = token_bytes(32)
        self.events = deque()
        self.lock = Lock()

    def allow(self, address: str | None) -> bool:
        digest = None
        if isinstance(address, str) and address:
            digest = blake2b(address.encode(), key=self.salt, digest_size=16).digest()
        with self.lock:
            now = monotonic()
            while self.events and self.events[0][0] <= now - self.window:
                self.events.popleft()
            if len(self.events) >= self.total:
                return False
            if digest is not None and sum(key == digest for _, key in self.events) >= self.per_address:
                return False
            self.events.append((now, digest))
            return True


SUBMISSION_LIMIT = RateLimiter(per_address=240, total=600)
LOGIN_LIMIT = RateLimiter(per_address=15, total=120)
