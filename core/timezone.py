from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Asia/Seoul")


def to_app_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_TIMEZONE)


def app_date(value: datetime) -> date:
    return to_app_timezone(value).date()


def app_now_date() -> date:
    return datetime.now(APP_TIMEZONE).date()


def app_day_bounds(day: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(day, time.min, tzinfo=APP_TIMEZONE)
    local_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=APP_TIMEZONE)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
