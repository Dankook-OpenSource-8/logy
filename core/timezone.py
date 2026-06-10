from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


KST_TIMEZONE_NAME = "Asia/Seoul"
APP_TIMEZONE = ZoneInfo(KST_TIMEZONE_NAME)
KST = APP_TIMEZONE


def to_app_timezone(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_TIMEZONE)


def to_kst(value: datetime | None) -> datetime | None:
    return to_app_timezone(value)


def app_date(value: datetime | None = None) -> date:
    value = value or datetime.now(timezone.utc)
    converted = to_app_timezone(value)
    if converted is None:
        return datetime.now(APP_TIMEZONE).date()
    return converted.date()


def kst_date(value: datetime | None = None) -> date:
    return app_date(value)


def app_now_date() -> date:
    return datetime.now(APP_TIMEZONE).date()


def app_day_bounds(day: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(day, time.min, tzinfo=APP_TIMEZONE)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def kst_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    return app_day_bounds(day)


def kst_date_range_bounds_utc(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_at, _ = app_day_bounds(start_date)
    _, end_at = app_day_bounds(end_date)
    return start_at, end_at
