from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


KST_TIMEZONE_NAME = "Asia/Seoul"
KST = ZoneInfo(KST_TIMEZONE_NAME)


def to_kst(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST)


def kst_date(value: datetime | None = None) -> date:
    value = value or datetime.now(timezone.utc)
    converted = to_kst(value)
    if converted is None:
        return datetime.now(KST).date()
    return converted.date()


def kst_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start_at_kst = datetime.combine(day, time.min, tzinfo=KST)
    end_at_kst = start_at_kst + timedelta(days=1)
    return start_at_kst.astimezone(timezone.utc), end_at_kst.astimezone(timezone.utc)


def kst_date_range_bounds_utc(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_at_kst = datetime.combine(start_date, time.min, tzinfo=KST)
    end_at_kst = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=KST)
    return start_at_kst.astimezone(timezone.utc), end_at_kst.astimezone(timezone.utc)
