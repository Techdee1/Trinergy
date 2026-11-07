"""Abuse and spend guards: per-IP rate limit, persisted server spend ledger."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path


class RateLimited(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.message, self.retry_after = message, retry_after


class RateLimiter:
    """Sliding windows per client key: `per_min` in 60 s and `per_day` in 24 h. In memory (one process)."""

    def __init__(self, per_min: int, per_day: int, clock=time.time):
        self.per_min, self.per_day, self.clock = per_min, per_day, clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self.clock()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - 86400:
                q.popleft()
            last_min = [t for t in q if t > now - 60]
            if len(last_min) >= self.per_min:
                wait = int(last_min[0] + 60 - now) + 1
                raise RateLimited(f"Rate limit: {self.per_min} questions per minute per client. Try again in {wait} s.", wait)
            if len(q) >= self.per_day:
                wait = int(q[0] + 86400 - now) + 1
                raise RateLimited(f"Rate limit: {self.per_day} questions per day per client. Try again in {wait // 60 + 1} min.", wait)
            q.append(now)


class SpendLedger:
    """Cumulative live spend of this server, persisted so a restart cannot reset the budget."""

    def __init__(self, path: Path, budget_usd: float):
        self.path, self.budget = Path(path), float(budget_usd)
        self._lock = threading.Lock()
        self.spent = 0.0
        self.requests = 0
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.spent, self.requests = float(d.get("spent_usd", 0.0)), int(d.get("live_requests", 0))
        except (OSError, ValueError):
            pass

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent)

    def add(self, usd: float) -> None:
        if usd <= 0:
            return
        with self._lock:
            self.spent += usd
            self.requests += 1
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"spent_usd": round(self.spent, 6), "live_requests": self.requests,
                                           "budget_usd": self.budget}), encoding="utf-8")
                tmp.replace(self.path)
            except OSError:
                pass
