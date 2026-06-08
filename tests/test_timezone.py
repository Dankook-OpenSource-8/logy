from datetime import date, datetime, timezone
import unittest

from core.timezone import app_date, app_day_bounds


class TimezoneTest(unittest.TestCase):
    def test_app_date_uses_korea_timezone(self):
        value = datetime(2026, 6, 7, 16, 0, tzinfo=timezone.utc)

        self.assertEqual(app_date(value), date(2026, 6, 8))

    def test_app_day_bounds_return_utc_range_for_korea_day(self):
        start_at, end_at = app_day_bounds(date(2026, 6, 8))

        self.assertEqual(start_at.isoformat(), "2026-06-07T15:00:00+00:00")
        self.assertEqual(end_at.isoformat(), "2026-06-08T15:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
