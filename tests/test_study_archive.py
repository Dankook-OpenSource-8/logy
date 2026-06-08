from datetime import datetime, timedelta, timezone
import unittest

from core.study_archive import (
    ArchiveAuthLog,
    ArchiveSession,
    build_daily_archive,
    build_monthly_archive,
    build_period_summary,
    build_weekly_archive,
)


def make_auth_log(
    auth_log_id: int,
    status: str,
    created_at: datetime,
) -> ArchiveAuthLog:
    return ArchiveAuthLog(
        auth_log_id=auth_log_id,
        status=status,
        video_url=f"https://storage.test/{auth_log_id}.mp4",
        thumbnail_url=None,
        verification_score=90 if status == "성공" else None,
        verification_reason="테스트 인증",
        created_at=created_at,
        verified_at=created_at + timedelta(seconds=3),
    )


def make_session(
    study_session_id: int,
    day: int,
    hour: int,
    status: str,
    total_minutes: int,
    auth_statuses: list[str] | None = None,
) -> ArchiveSession:
    start_time = datetime(2026, 5, day, hour, 0, tzinfo=timezone.utc)
    return ArchiveSession(
        study_session_id=study_session_id,
        subject="자료구조",
        goal_note="챕터 복습",
        start_time=start_time,
        end_time=start_time + timedelta(minutes=total_minutes),
        total_seconds=total_minutes * 60,
        status=status,
        auth_logs=[
            make_auth_log(study_session_id * 10 + index, auth_status, start_time + timedelta(minutes=index))
            for index, auth_status in enumerate(auth_statuses or [], start=1)
        ],
    )


class StudyArchiveTest(unittest.TestCase):
    def test_empty_daily_archive_returns_empty_list(self):
        self.assertEqual(build_daily_archive([]), [])

    def test_daily_archive_groups_sessions_by_date(self):
        sessions = [
            make_session(1, 18, 9, "completed", 60),
            make_session(2, 18, 12, "failed", 10),
            make_session(3, 19, 9, "completed", 30),
        ]

        result = build_daily_archive(sessions)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["date"].isoformat(), "2026-05-19")
        self.assertEqual(result[1]["sessionCount"], 2)

    def test_daily_archive_uses_korea_date_for_early_morning_records(self):
        utc_afternoon = datetime(2026, 6, 7, 16, 30, tzinfo=timezone.utc)
        session = ArchiveSession(
            study_session_id=1,
            subject="데이터베이스",
            goal_note=None,
            start_time=utc_afternoon,
            end_time=utc_afternoon + timedelta(minutes=30),
            total_seconds=1800,
            status="completed",
            auth_logs=[],
        )

        result = build_daily_archive([session])

        self.assertEqual(result[0]["date"].isoformat(), "2026-06-08")

    def test_daily_archive_sums_study_seconds(self):
        result = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60),
                make_session(2, 18, 12, "failed", 10),
            ]
        )

        self.assertEqual(result[0]["totalSeconds"], 4200)

    def test_daily_archive_counts_completed_and_failed_sessions(self):
        result = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60),
                make_session(2, 18, 12, "failed", 10),
                make_session(3, 18, 13, "cancelled", 5),
            ]
        )

        self.assertEqual(result[0]["completedCount"], 1)
        self.assertEqual(result[0]["failedCount"], 1)

    def test_daily_archive_counts_auth_log_statuses(self):
        result = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60, ["성공", "성공"]),
                make_session(2, 18, 12, "failed", 10, ["실패", "시간초과", "대기"]),
            ]
        )

        day = result[0]
        self.assertEqual(day["authSuccessCount"], 2)
        self.assertEqual(day["authFailedCount"], 1)
        self.assertEqual(day["authTimeoutCount"], 1)
        self.assertEqual(day["authPendingCount"], 1)

    def test_session_payload_contains_auth_video_summary(self):
        result = build_daily_archive([make_session(1, 18, 9, "completed", 60, ["성공"])])
        session = result[0]["sessions"][0]

        self.assertEqual(session["studySessionId"], 1)
        self.assertEqual(session["authLogs"][0]["videoUrl"], "https://storage.test/11.mp4")
        self.assertEqual(session["authLogs"][0]["verificationScore"], 90)

    def test_sessions_are_sorted_latest_first_inside_day(self):
        result = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60),
                make_session(2, 18, 12, "completed", 20),
            ]
        )

        self.assertEqual(result[0]["sessions"][0]["studySessionId"], 2)

    def test_auth_logs_are_sorted_by_created_time(self):
        session = make_session(1, 18, 9, "completed", 60, [])
        later = make_auth_log(2, "성공", session.start_time + timedelta(minutes=2))
        earlier = make_auth_log(1, "성공", session.start_time + timedelta(minutes=1))
        session = ArchiveSession(**{**session.__dict__, "auth_logs": [later, earlier]})

        result = build_daily_archive([session])

        self.assertEqual([item["authLogId"] for item in result[0]["sessions"][0]["authLogs"]], [1, 2])

    def test_period_summary_aggregates_days(self):
        days = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60, ["성공"]),
                make_session(2, 19, 9, "failed", 10, ["실패"]),
            ]
        )

        result = build_period_summary(
            days,
            datetime(2026, 5, 18, tzinfo=timezone.utc).date(),
            datetime(2026, 5, 19, tzinfo=timezone.utc).date(),
            "custom",
        )

        self.assertEqual(result["totalSeconds"], 4200)
        self.assertEqual(result["sessionCount"], 2)
        self.assertEqual(result["averageDailySeconds"], 2100)

    def test_weekly_archive_uses_iso_week_label(self):
        days = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60),
                make_session(2, 19, 9, "completed", 60),
            ]
        )

        result = build_weekly_archive(days)

        self.assertEqual(result[0]["period"], "2026-W21")
        self.assertEqual(result[0]["startDate"].isoformat(), "2026-05-18")
        self.assertEqual(result[0]["endDate"].isoformat(), "2026-05-24")

    def test_weekly_archive_splits_different_weeks(self):
        days = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60),
                make_session(2, 25, 9, "completed", 60),
            ]
        )

        result = build_weekly_archive(days)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["period"], "2026-W22")

    def test_monthly_archive_uses_month_label(self):
        days = build_daily_archive(
            [
                make_session(1, 18, 9, "completed", 60),
                make_session(2, 19, 9, "completed", 60),
            ]
        )

        result = build_monthly_archive(days)

        self.assertEqual(result[0]["period"], "2026-05")
        self.assertEqual(result[0]["startDate"].isoformat(), "2026-05-01")
        self.assertEqual(result[0]["endDate"].isoformat(), "2026-05-31")

    def test_monthly_archive_splits_different_months(self):
        may = make_session(1, 31, 9, "completed", 60)
        june_start = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        june = ArchiveSession(
            study_session_id=2,
            subject="영어",
            goal_note=None,
            start_time=june_start,
            end_time=june_start + timedelta(minutes=30),
            total_seconds=1800,
            status="completed",
            auth_logs=[],
        )

        result = build_monthly_archive(build_daily_archive([may, june]))

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["period"], "2026-06")

    def test_zero_length_period_still_has_safe_average(self):
        day = datetime(2026, 5, 18, tzinfo=timezone.utc).date()
        result = build_period_summary([], day, day, "empty")

        self.assertEqual(result["averageDailySeconds"], 0)

    def test_pending_auth_includes_unknown_status(self):
        result = build_daily_archive([make_session(1, 18, 9, "completed", 60, ["검증중"])])

        self.assertEqual(result[0]["authPendingCount"], 1)


if __name__ == "__main__":
    unittest.main()
