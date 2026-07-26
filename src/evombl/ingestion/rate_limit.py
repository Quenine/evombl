import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitPolicy:
    minimum_interval: float
    max_attempts: int = 3


POLICIES = {
    "crossref": RateLimitPolicy(0.1),
    "europe_pmc": RateLimitPolicy(0.1),
    "ncbi": RateLimitPolicy(1 / 3),
    "ncbi_api_key": RateLimitPolicy(0.1),
    "rcsb_pdb": RateLimitPolicy(0.1),
}


class RateLimiter:
    def __init__(
        self,
        policy: RateLimitPolicy,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy
        self.clock = clock
        self.sleeper = sleeper
        self.last_request: float | None = None

    def acquire(self, retry_after: float | None = None) -> None:
        now = self.clock()
        delay = retry_after or 0.0
        if self.last_request is not None:
            delay = max(delay, self.policy.minimum_interval - (now - self.last_request))
        if delay > 0:
            self.sleeper(delay)
        self.last_request = self.clock()


def policy_for(provider: str, *, ncbi_api_key: bool = False) -> RateLimitPolicy:
    key = "ncbi_api_key" if provider == "ncbi" and ncbi_api_key else provider
    try:
        return POLICIES[key]
    except KeyError as exc:
        raise ValueError(f"unknown rate-limit provider: {provider}") from exc
