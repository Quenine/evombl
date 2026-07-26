import pytest

from evombl.ingestion.rate_limit import RateLimiter, policy_for


def test_provider_and_ncbi_key_policies() -> None:
    assert policy_for("ncbi").minimum_interval == pytest.approx(1 / 3)
    assert policy_for("ncbi", ncbi_api_key=True).minimum_interval == pytest.approx(0.1)
    assert policy_for("crossref").minimum_interval == pytest.approx(0.1)


def test_injected_clock_and_rapid_request_protection() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleeper(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    limiter = RateLimiter(policy_for("europe_pmc"), clock, sleeper)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire(retry_after=2.0)
    assert sleeps == pytest.approx([0.1, 2.0])
