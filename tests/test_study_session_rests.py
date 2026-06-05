from datetime import datetime, timezone
import unittest

from api.routes import REST_DAILY_MAX_COUNT, REST_DAILY_MAX_SECONDS
from schemas.user import (
    StudySessionRestEndResponse,
    StudySessionRestStartResponse,
    StudySessionRestStatusResponse,
)


class StudySessionRestSchemaTest(unittest.TestCase):
    def test_rest_limits_match_timer_policy(self):
        self.assertEqual(REST_DAILY_MAX_COUNT, 2)
        self.assertEqual(REST_DAILY_MAX_SECONDS, 900)

    def test_rest_status_response_contains_remaining_limits(self):
        payload = StudySessionRestStatusResponse(
            study_session_id=1,
            is_paused=False,
            daily_rest_count=1,
            daily_rest_seconds=300,
            remaining_rest_count=1,
            remaining_rest_seconds=600,
            active_rest_id=None,
            active_rest_started_at=None,
        )

        self.assertEqual(payload.remaining_rest_count, 1)
        self.assertEqual(payload.remaining_rest_seconds, 600)

    def test_rest_start_response_exposes_active_rest(self):
        started_at = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
        payload = StudySessionRestStartResponse(
            message="휴식 시작",
            rest_id=7,
            study_session_id=1,
            is_paused=True,
            daily_rest_count=1,
            daily_rest_seconds=0,
            remaining_rest_count=1,
            remaining_rest_seconds=900,
            active_rest_id=7,
            active_rest_started_at=started_at,
        )

        self.assertEqual(payload.rest_id, 7)
        self.assertTrue(payload.is_paused)
        self.assertEqual(payload.active_rest_started_at, started_at)

    def test_rest_end_response_exposes_used_seconds(self):
        payload = StudySessionRestEndResponse(
            message="휴식 종료",
            rest_id=7,
            rest_seconds=420,
            study_session_id=1,
            is_paused=False,
            daily_rest_count=1,
            daily_rest_seconds=420,
            remaining_rest_count=1,
            remaining_rest_seconds=480,
            active_rest_id=None,
            active_rest_started_at=None,
        )

        self.assertEqual(payload.rest_seconds, 420)
        self.assertFalse(payload.is_paused)


if __name__ == "__main__":
    unittest.main()
