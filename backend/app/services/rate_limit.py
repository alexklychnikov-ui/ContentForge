from collections import defaultdict
from time import time

from app.errors import AppError

WINDOW_SECONDS = 10 * 60
MAX_FAILURES = 5


class LoginRateLimiter:
    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = defaultdict(list)

    def _key(self, ip: str, email: str) -> str:
        return f"{ip}:{email.strip().lower()}"

    def _prune(self, key: str, now: float) -> list[float]:
        cutoff = now - WINDOW_SECONDS
        kept = [stamp for stamp in self._failures[key] if stamp > cutoff]
        self._failures[key] = kept
        return kept

    def check(self, ip: str, email: str) -> None:
        key = self._key(ip, email)
        stamps = self._prune(key, time())
        if len(stamps) >= MAX_FAILURES:
            raise AppError(
                429,
                "rate_limited",
                "Слишком много неудачных попыток входа. Подождите 10 минут.",
            )

    def record_failure(self, ip: str, email: str) -> None:
        key = self._key(ip, email)
        now = time()
        stamps = self._prune(key, now)
        stamps.append(now)
        self._failures[key] = stamps

    def reset(self, ip: str, email: str) -> None:
        self._failures.pop(self._key(ip, email), None)

    def clear(self) -> None:
        self._failures.clear()


login_rate_limiter = LoginRateLimiter()
