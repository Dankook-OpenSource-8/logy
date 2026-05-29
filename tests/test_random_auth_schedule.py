from datetime import datetime, timezone
from random import Random
import unittest

from core.random_auth_schedule import (
    AUTH_DELAY_MINUTES,
    AUTH_RESPONSE_LIMIT_SECONDS,
    auth_expires_at,
    is_auth_expired,
    next_auth_time_from,
    weighted_auth_delay_minutes,
)


class RandomAuthScheduleTest(unittest.TestCase):
    def test_weighted_delay_is_always_between_50_and_70_minutes(self):
        rng = Random(42)

        results = [weighted_auth_delay_minutes(rng) for _ in range(200)]

        self.assertTrue(all(50 <= minute <= 70 for minute in results))

    def test_middle_minutes_have_higher_weight_than_edges(self):
        rng = Random(7)
        results = [weighted_auth_delay_minutes(rng) for _ in range(1000)]
        middle_count = sum(58 <= minute <= 62 for minute in results)
        edge_count = sum(minute in {50, 51, 69, 70} for minute in results)

        self.assertGreater(middle_count, edge_count)

    def test_auth_delay_minutes_cover_expected_range(self):
        self.assertEqual(AUTH_DELAY_MINUTES[0], 50)
        self.assertEqual(AUTH_DELAY_MINUTES[-1], 70)

    def test_next_auth_time_uses_weighted_delay(self):
        start_time = datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc)
        rng = Random(1)

        next_auth_time = next_auth_time_from(start_time, rng)
        delay_seconds = (next_auth_time - start_time).total_seconds()

        self.assertIn(delay_seconds // 60, AUTH_DELAY_MINUTES)

    def test_auth_expires_at_is_60_seconds_after_next_auth_time(self):
        next_auth_time = datetime(2026, 5, 29, 12, 50, tzinfo=timezone.utc)

        expires_at = auth_expires_at(next_auth_time)

        self.assertEqual(
            (expires_at - next_auth_time).total_seconds(),
            AUTH_RESPONSE_LIMIT_SECONDS,
        )

    def test_auth_expiration_is_strictly_after_deadline(self):
        next_auth_time = datetime(2026, 5, 29, 12, 50, tzinfo=timezone.utc)
        expires_at = auth_expires_at(next_auth_time)

        self.assertFalse(is_auth_expired(expires_at, next_auth_time))
        self.assertTrue(is_auth_expired(expires_at.replace(microsecond=1), next_auth_time))


if __name__ == "__main__":
    unittest.main()
