from datetime import datetime, time, timezone
from types import SimpleNamespace
import unittest

from fastapi import HTTPException

from api.routes import (
    _notification_settings_response,
    _notification_weekdays_to_db,
    _notification_weekdays_to_list,
)
from schemas import NotificationSettingsUpdateRequest


class NotificationSettingsTest(unittest.TestCase):
    def test_weekdays_are_sorted_and_deduplicated_for_storage(self):
        self.assertEqual(_notification_weekdays_to_db([4, 1, 1, 0]), "0,1,4")

    def test_empty_weekdays_are_stored_as_empty_string(self):
        self.assertEqual(_notification_weekdays_to_db([]), "")
        self.assertEqual(_notification_weekdays_to_db(None), "")

    def test_invalid_weekday_is_rejected(self):
        with self.assertRaises(HTTPException):
            _notification_weekdays_to_db([0, 7])

    def test_weekdays_are_restored_from_storage(self):
        self.assertEqual(_notification_weekdays_to_list("0,1,4"), [0, 1, 4])

    def test_update_request_defaults_match_mypage_notification_screen(self):
        payload = NotificationSettingsUpdateRequest()

        self.assertTrue(payload.all_notifications_enabled)
        self.assertTrue(payload.random_auth_enabled)
        self.assertTrue(payload.group_enabled)
        self.assertTrue(payload.reward_enabled)
        self.assertFalse(payload.quiet_hours_enabled)
        self.assertEqual(payload.quiet_weekdays, [0, 1, 2, 3, 4])

    def test_update_request_accepts_empty_quiet_values_when_disabled(self):
        payload = NotificationSettingsUpdateRequest(
            quiet_hours_enabled=False,
            quiet_start_time="",
            quiet_end_time="",
            quiet_weekdays="",
        )

        self.assertFalse(payload.quiet_hours_enabled)
        self.assertIsNone(payload.quiet_start_time)
        self.assertIsNone(payload.quiet_end_time)
        self.assertEqual(payload.quiet_weekdays, [])

    def test_update_request_accepts_frontend_camel_case_empty_quiet_values(self):
        payload = NotificationSettingsUpdateRequest.model_validate({
            "allNotificationsEnabled": True,
            "randomAuthEnabled": True,
            "groupEnabled": True,
            "rewardEnabled": True,
            "quietHoursEnabled": False,
            "quietStartTime": "",
            "quietEndTime": "",
            "quietWeekdays": [],
        })

        self.assertFalse(payload.quiet_hours_enabled)
        self.assertIsNone(payload.quiet_start_time)
        self.assertIsNone(payload.quiet_end_time)
        self.assertEqual(payload.quiet_weekdays, [])

    def test_response_uses_frontend_friendly_field_names(self):
        now = datetime(2026, 6, 8, 15, 0, tzinfo=timezone.utc)
        setting = SimpleNamespace(
            all_notifications_enabled=True,
            random_auth_enabled=False,
            group_enabled=True,
            reward_enabled=True,
            quiet_hours_enabled=True,
            quiet_start_time=time(23, 0),
            quiet_end_time=time(8, 0),
            quiet_weekdays="0,1,2,3,4",
            created_at=now,
            updated_at=now,
        )

        response = _notification_settings_response(setting, "알림 설정 저장")

        self.assertEqual(response.message, "알림 설정 저장")
        self.assertFalse(response.randomAuthEnabled)
        self.assertEqual(response.quietStartTime, time(23, 0))
        self.assertEqual(response.quietWeekdays, [0, 1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
