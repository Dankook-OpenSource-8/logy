import random
from datetime import datetime, timedelta
from random import Random


AUTH_DELAY_MINUTES = tuple(range(5, 7))
AUTH_RESPONSE_LIMIT_SECONDS = 120


def weighted_auth_delay_minutes(rng: Random | None = None) -> int:
    generator = rng or random
    weights = [1 for _ in AUTH_DELAY_MINUTES]
    return generator.choices(AUTH_DELAY_MINUTES, weights=weights, k=1)[0]


def next_auth_time_from(start_time: datetime, rng: Random | None = None) -> datetime:
    return start_time + timedelta(minutes=weighted_auth_delay_minutes(rng))


def auth_expires_at(next_auth_time: datetime) -> datetime:
    return next_auth_time + timedelta(seconds=AUTH_RESPONSE_LIMIT_SECONDS)


def is_auth_expired(now: datetime, next_auth_time: datetime) -> bool:
    return now > auth_expires_at(next_auth_time)
