from datetime import datetime, timedelta, timezone
import unittest

from core.focus_analytics import AnalyticsSession, build_focus_analytics


def make_session(
    day: int,
    hour: int,
    status: str,
    duration_minutes: int = 30,
) -> AnalyticsSession:
    start_time = datetime(2026, 5, day, hour, 0, tzinfo=timezone.utc)
    end_time = start_time + timedelta(minutes=duration_minutes)
    return AnalyticsSession(
        start_time=start_time,
        end_time=end_time,
        status=status,
        total_seconds=duration_minutes * 60,
    )


class FocusAnalyticsTest(unittest.TestCase):
    def test_empty_sessions_returns_safe_defaults(self):
        result = build_focus_analytics([])

        self.assertEqual(result["riskMap"], [])
        self.assertIsNone(result["collapsePrediction"]["predictedCollapseMinute"])
        self.assertFalse(result["metadata"]["isEnoughData"])

    def test_generates_risk_map_for_observed_day_hour_slots(self):
        sessions = [
            make_session(18, 22, "failed", 18),
            make_session(18, 22, "completed", 45),
            make_session(19, 9, "completed", 50),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(len(result["riskMap"]), 2)
        tuesday_7 = next(
            item
            for item in result["riskMap"]
            if item["dayOfWeek"] == 1 and item["hour"] == 7
        )
        self.assertEqual(tuesday_7["totalAttempts"], 2)
        self.assertEqual(tuesday_7["failedAttempts"], 1)
        self.assertEqual(tuesday_7["failureRate"], 50.0)

    def test_collapse_prediction_uses_median_and_trims_outlier(self):
        sessions = [
            make_session(11, 21, "failed", 15),
            make_session(12, 21, "failed", 17),
            make_session(13, 21, "failed", 18),
            make_session(14, 21, "failed", 19),
            make_session(15, 21, "failed", 180),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["collapsePrediction"]["predictedCollapseMinute"], 18)
        self.assertEqual(result["collapsePrediction"]["riskStartMinute"], 14)
        self.assertEqual(result["collapsePrediction"]["sampleSize"], 4)

    def test_recent_failure_trend_increases_latest_slot_risk(self):
        older_completed = [make_session(day, 8, "completed", 45) for day in range(1, 9)]
        recent_failed = [make_session(day, 23, "failed", 12) for day in range(10, 15)]

        result = build_focus_analytics(older_completed + recent_failed)
        high_risk_slot = next(item for item in result["riskMap"] if item["hour"] == 8)

        self.assertIn(high_risk_slot["riskLevel"], {"HIGH", "CRITICAL"})
        self.assertGreater(result["metadata"]["recentFailureRate"], result["metadata"]["baselineFailureRate"])

    def test_summary_reports_highest_risk_slot_and_recommendation(self):
        sessions = [
            make_session(18, 22, "failed", 13),
            make_session(18, 22, "failed", 14),
            make_session(18, 22, "completed", 60),
            make_session(19, 10, "completed", 60),
            make_session(20, 10, "completed", 60),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["summary"]["highestRiskDay"], "화요일")
        self.assertEqual(result["summary"]["highestRiskHour"], 7)
        self.assertGreater(result["summary"]["riskMultiplier"], 1)
        self.assertTrue(result["summary"]["recommendation"])

    def test_active_sessions_are_excluded_from_attempt_count(self):
        sessions = [
            make_session(18, 10, "active", 5),
            make_session(18, 11, "completed", 40),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["metadata"]["totalAttempts"], 1)
        self.assertEqual(len(result["riskMap"]), 1)

    def test_cancelled_sessions_count_as_attempts_but_not_failures(self):
        sessions = [
            make_session(18, 10, "cancelled", 10),
            make_session(18, 10, "failed", 10),
        ]

        result = build_focus_analytics(sessions)
        slot = result["riskMap"][0]

        self.assertEqual(result["metadata"]["totalAttempts"], 2)
        self.assertEqual(result["metadata"]["failedAttempts"], 1)
        self.assertEqual(slot["failureRate"], 50.0)

    def test_completed_only_sessions_have_no_collapse_prediction(self):
        sessions = [make_session(day, 9, "completed", 45) for day in range(18, 23)]

        result = build_focus_analytics(sessions)

        self.assertIsNone(result["collapsePrediction"]["predictedCollapseMinute"])
        self.assertEqual(result["collapsePrediction"]["riskLevel"], "LOW")

    def test_duration_falls_back_to_total_seconds_when_end_time_missing(self):
        start_time = datetime(2026, 5, 18, 13, 0, tzinfo=timezone.utc)
        session = AnalyticsSession(
            start_time=start_time,
            end_time=None,
            status="failed",
            total_seconds=17 * 60,
        )

        result = build_focus_analytics([session])

        self.assertEqual(result["collapsePrediction"]["predictedCollapseMinute"], 17)

    def test_non_positive_duration_is_not_used_for_collapse_sample(self):
        sessions = [
            make_session(18, 13, "failed", -5),
            make_session(19, 13, "failed", 20),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["collapsePrediction"]["predictedCollapseMinute"], 20)
        self.assertEqual(result["collapsePrediction"]["sampleSize"], 1)

    def test_risk_score_is_capped_at_100(self):
        sessions = [make_session(day, 23, "failed", 5) for day in range(18, 28)]

        result = build_focus_analytics(sessions)

        self.assertLessEqual(max(item["riskScore"] for item in result["riskMap"]), 100.0)

    def test_all_failed_short_sessions_become_critical(self):
        sessions = [make_session(day, 23, "failed", 8) for day in range(18, 23)]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["riskMap"][0]["riskLevel"], "CRITICAL")

    def test_stable_successful_pattern_stays_low_risk(self):
        sessions = [make_session(day, 7, "completed", 60) for day in range(18, 23)]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["riskMap"][0]["riskLevel"], "LOW")
        self.assertEqual(result["metadata"]["baselineFailureRate"], 0.0)

    def test_single_slot_reason_mentions_low_sample_size(self):
        result = build_focus_analytics([make_session(18, 17, "failed", 12)])

        self.assertIn("참고용", result["riskMap"][0]["reason"])

    def test_repeated_slot_reason_mentions_baseline_when_above_average(self):
        sessions = [
            make_session(18, 22, "failed", 12),
            make_session(18, 22, "failed", 13),
            make_session(19, 9, "completed", 40),
            make_session(20, 9, "completed", 40),
        ]

        result = build_focus_analytics(sessions)
        risky_slot = next(item for item in result["riskMap"] if item["hour"] == 7)

        self.assertIn("개인 평균보다", risky_slot["reason"])

    def test_stable_slot_reason_mentions_personal_average(self):
        sessions = [
            make_session(18, 9, "completed", 40),
            make_session(18, 9, "completed", 40),
            make_session(19, 22, "failed", 12),
            make_session(20, 22, "failed", 12),
        ]

        result = build_focus_analytics(sessions)
        stable_slot = next(item for item in result["riskMap"] if item["hour"] == 18)

        self.assertIn("안정적인", stable_slot["reason"])

    def test_risk_start_minute_is_at_least_one(self):
        result = build_focus_analytics([make_session(18, 22, "failed", 1)])

        self.assertEqual(result["collapsePrediction"]["riskStartMinute"], 1)

    def test_recent_failed_limit_uses_latest_10_failures(self):
        old_failures = [make_session(day, 8, "failed", 90) for day in range(1, 6)]
        recent_failures = [make_session(day, 8, "failed", 10) for day in range(10, 20)]

        result = build_focus_analytics(old_failures + recent_failures)

        self.assertEqual(result["collapsePrediction"]["predictedCollapseMinute"], 10)
        self.assertEqual(result["collapsePrediction"]["sampleSize"], 10)

    def test_recent_session_limit_defaults_to_latest_10_sessions(self):
        old_completed = [make_session(day, 9, "completed", 40) for day in range(1, 6)]
        recent_failed = [make_session(day, 9, "failed", 15) for day in range(10, 20)]

        result = build_focus_analytics(old_completed + recent_failed)

        self.assertEqual(result["metadata"]["baselineFailureRate"], 66.7)
        self.assertEqual(result["metadata"]["recentFailureRate"], 100.0)

    def test_custom_recent_session_limit_is_applied(self):
        sessions = [
            make_session(18, 9, "completed", 40),
            make_session(19, 9, "completed", 40),
            make_session(20, 9, "failed", 15),
            make_session(21, 9, "failed", 15),
        ]

        result = build_focus_analytics(sessions, recent_session_limit=2)

        self.assertEqual(result["metadata"]["recentFailureRate"], 100.0)

    def test_custom_recent_failed_limit_is_applied(self):
        sessions = [
            make_session(18, 9, "failed", 50),
            make_session(19, 9, "failed", 10),
            make_session(20, 9, "failed", 12),
        ]

        result = build_focus_analytics(sessions, recent_failed_limit=2)

        self.assertEqual(result["collapsePrediction"]["predictedCollapseMinute"], 11)
        self.assertEqual(result["collapsePrediction"]["sampleSize"], 2)

    def test_sunday_maps_to_six_for_monday_first_frontend_heatmap(self):
        result = build_focus_analytics([make_session(3, 9, "completed", 40)])

        self.assertEqual(result["riskMap"][0]["dayOfWeek"], 6)
        self.assertEqual(result["summary"]["highestRiskDay"], "일요일")

    def test_hour_is_converted_to_kst_for_frontend_heatmap(self):
        result = build_focus_analytics([make_session(18, 0, "failed", 15)])

        self.assertEqual(result["riskMap"][0]["hour"], 9)
        self.assertEqual(result["metadata"]["timezone"], "Asia/Seoul")

    def test_enough_data_requires_at_least_five_attempts_and_one_failure(self):
        four_sessions = [
            make_session(18, 9, "completed", 40),
            make_session(19, 9, "completed", 40),
            make_session(20, 9, "completed", 40),
            make_session(21, 9, "failed", 15),
        ]
        five_sessions = four_sessions + [make_session(22, 9, "completed", 40)]

        self.assertFalse(build_focus_analytics(four_sessions)["metadata"]["isEnoughData"])
        self.assertTrue(build_focus_analytics(five_sessions)["metadata"]["isEnoughData"])

    def test_summary_has_safe_defaults_when_baseline_has_no_failures(self):
        result = build_focus_analytics([make_session(18, 9, "completed", 40)])

        self.assertEqual(result["summary"]["riskMultiplier"], 0.0)
        self.assertEqual(result["summary"]["recommendation"], "현재 패턴은 안정적입니다. 지금의 학습 루틴을 유지해보세요.")

    def test_metadata_counts_failed_attempts_across_slots(self):
        sessions = [
            make_session(18, 8, "failed", 15),
            make_session(18, 9, "completed", 45),
            make_session(19, 10, "failed", 20),
            make_session(20, 11, "cancelled", 5),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["metadata"]["totalAttempts"], 4)
        self.assertEqual(result["metadata"]["failedAttempts"], 2)

    def test_risk_map_is_sorted_by_day_then_hour(self):
        sessions = [
            make_session(19, 22, "completed", 40),
            make_session(18, 9, "completed", 40),
            make_session(18, 7, "failed", 15),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(
            [(item["dayOfWeek"], item["hour"]) for item in result["riskMap"]],
            [(0, 16), (0, 18), (2, 7)],
        )

    def test_output_values_are_rounded_for_api_response(self):
        sessions = [
            make_session(18, 9, "failed", 15),
            make_session(18, 9, "completed", 45),
            make_session(18, 9, "completed", 45),
        ]

        result = build_focus_analytics(sessions)

        self.assertEqual(result["riskMap"][0]["failureRate"], 33.3)
        self.assertEqual(result["metadata"]["baselineFailureRate"], 33.3)


if __name__ == "__main__":
    unittest.main()
