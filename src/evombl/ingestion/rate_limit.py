import time
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RateLimitPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    minimum_interval: float = Field(ge=0)
    retry_count: int = Field(ge=1, le=10)
    base_backoff: float = Field(ge=0)
    maximum_backoff: float = Field(ge=0)
    honor_retry_after: bool


class RateLimitConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    configuration_version: str
    providers: dict[str, RateLimitPolicy]


def load_rate_limits(path: Path = Path("config/source_rate_limits.yaml")) -> RateLimitConfiguration:
    return RateLimitConfiguration.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


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


def policy_for(
    configuration: RateLimitConfiguration, provider: str, *, ncbi_api_key: bool = False
) -> RateLimitPolicy:
    key = (
        ("ncbi_api_key" if ncbi_api_key else "ncbi_no_key")
        if provider.startswith("ncbi")
        else provider
    )
    try:
        return configuration.providers[key]
    except KeyError as exc:
        raise ValueError(f"missing rate-limit provider: {key}") from exc
