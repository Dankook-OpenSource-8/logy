from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class ArchiveAuthLog:
    auth_log_id: int
    status: str
    video_url: str
    thumbnail_url: str | None
    verification_score: int | None
    verification_reason: str | None
    created_at: datetime
    verified_at: datetime | None


@dataclass(frozen=True)
class ArchiveSession:
    study_session_id: int
    subject: str | None
    goal_note: str | None
    start_time: datetime
    end_time: datetime | None
    total_seconds: int
    status: str
    auth_logs: list[ArchiveAuthLog]


def _auth_counts(auth_logs: list[ArchiveAuthLog]) -> dict[str, int]:
    counts = {
        "authSuccessCount": 0,
        "authFailedCount": 0,
        "authPendingCount": 0,
        "authTimeoutCount": 0,
    }
    for auth_log in auth_logs:
        if auth_log.status == "성공":
            counts["authSuccessCount"] += 1
        elif auth_log.status == "실패":
            counts["authFailedCount"] += 1
        elif auth_log.status == "시간초과":
            counts["authTimeoutCount"] += 1
        else:
            counts["authPendingCount"] += 1
    return counts


def _session_payload(session: ArchiveSession) -> dict:
    counts = _auth_counts(session.auth_logs)
    return {
        "studySessionId": session.study_session_id,
        "subject": session.subject,
        "goalNote": session.goal_note,
        "startTime": session.start_time,
        "endTime": session.end_time,
        "totalSeconds": int(session.total_seconds or 0),
        "status": session.status,
        **counts,
        "authLogs": [
            {
                "authLogId": auth_log.auth_log_id,
                "status": auth_log.status,
                "videoUrl": auth_log.video_url,
                "thumbnailUrl": auth_log.thumbnail_url,
                "verificationScore": auth_log.verification_score,
                "verificationReason": auth_log.verification_reason,
                "createdAt": auth_log.created_at,
                "verifiedAt": auth_log.verified_at,
            }
            for auth_log in sorted(auth_log_iter(session), key=lambda item: item.created_at)
        ],
    }


def auth_log_iter(session: ArchiveSession) -> list[ArchiveAuthLog]:
    return session.auth_logs or []


def build_daily_archive(sessions: list[ArchiveSession]) -> list[dict]:
    days: dict[date, list[ArchiveSession]] = defaultdict(list)
    for session in sessions:
        days[session.start_time.date()].append(session)

    daily_archive = []
    for archive_date in sorted(days.keys(), reverse=True):
        day_sessions = sorted(days[archive_date], key=lambda item: item.start_time, reverse=True)
        session_payloads = [_session_payload(session) for session in day_sessions]
        auth_logs = [auth_log for session in day_sessions for auth_log in auth_log_iter(session)]
        counts = _auth_counts(auth_logs)
        daily_archive.append(
            {
                "date": archive_date,
                "totalSeconds": sum(item["totalSeconds"] for item in session_payloads),
                "sessionCount": len(day_sessions),
                "completedCount": sum(1 for session in day_sessions if session.status == "completed"),
                "failedCount": sum(1 for session in day_sessions if session.status == "failed"),
                **counts,
                "sessions": session_payloads,
            }
        )
    return daily_archive


def build_period_summary(
    days: list[dict],
    start_date: date,
    end_date: date,
    period_label: str,
) -> dict:
    total_days = max((end_date - start_date).days + 1, 1)
    total_seconds = sum(day["totalSeconds"] for day in days)
    return {
        "period": period_label,
        "startDate": start_date,
        "endDate": end_date,
        "totalSeconds": total_seconds,
        "sessionCount": sum(day["sessionCount"] for day in days),
        "completedCount": sum(day["completedCount"] for day in days),
        "failedCount": sum(day["failedCount"] for day in days),
        "authSuccessCount": sum(day["authSuccessCount"] for day in days),
        "authFailedCount": sum(day["authFailedCount"] for day in days),
        "authPendingCount": sum(day["authPendingCount"] for day in days),
        "authTimeoutCount": sum(day["authTimeoutCount"] for day in days),
        "averageDailySeconds": round(total_seconds / total_days),
        "days": sorted(days, key=lambda item: item["date"], reverse=True),
    }


def build_weekly_archive(days: list[dict]) -> list[dict]:
    grouped_days: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for day in days:
        iso_year, iso_week, _ = day["date"].isocalendar()
        grouped_days[(iso_year, iso_week)].append(day)

    summaries = []
    for (iso_year, iso_week), week_days in grouped_days.items():
        monday = date.fromisocalendar(iso_year, iso_week, 1)
        sunday = monday + timedelta(days=6)
        summaries.append(build_period_summary(week_days, monday, sunday, f"{iso_year}-W{iso_week:02d}"))
    return sorted(summaries, key=lambda item: item["startDate"], reverse=True)


def build_monthly_archive(days: list[dict]) -> list[dict]:
    grouped_days: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for day in days:
        grouped_days[(day["date"].year, day["date"].month)].append(day)

    summaries = []
    for (year, month), month_days in grouped_days.items():
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        summaries.append(build_period_summary(month_days, start_date, end_date, f"{year}-{month:02d}"))
    return sorted(summaries, key=lambda item: item["startDate"], reverse=True)
