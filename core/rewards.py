from dataclasses import dataclass
from datetime import date, timedelta


PET_EVOLUTION_STAGES = [
    {"level": 1, "name": "알/새싹", "requiredExp": 0},
    {"level": 2, "name": "아기 펫", "requiredExp": 20},
    {"level": 3, "name": "학생 펫", "requiredExp": 80},
    {"level": 4, "name": "전공 펫", "requiredExp": 200},
    {"level": 5, "name": "마스터 펫", "requiredExp": 400},
]


@dataclass(frozen=True)
class AttendanceReward:
    streak_days: int
    bonus_exp: int
    is_first_attendance_today: bool


def pet_exp_from_verified_seconds(verified_seconds: int) -> int:
    return max(verified_seconds, 0) // 300


def pet_level_from_exp(total_exp: int) -> int:
    level = 1
    for stage in PET_EVOLUTION_STAGES:
        if total_exp >= stage["requiredExp"]:
            level = stage["level"]
    return level


def pet_stage_name(level: int) -> str:
    for stage in PET_EVOLUTION_STAGES:
        if stage["level"] == level:
            return stage["name"]
    return PET_EVOLUTION_STAGES[0]["name"]


def next_pet_stage(total_exp: int) -> dict | None:
    current_level = pet_level_from_exp(total_exp)
    for stage in PET_EVOLUTION_STAGES:
        if stage["level"] > current_level:
            return stage
    return None


def furniture_progress_from_auth_minutes(auth_minutes: int) -> int:
    if auth_minutes < 15:
        return 5
    if auth_minutes < 35:
        return 10
    if auth_minutes < 50:
        return 15
    if auth_minutes < 60:
        return 20
    if auth_minutes < 70:
        return 25
    if auth_minutes < 80:
        return 30
    if auth_minutes < 90:
        return 35
    return 40


def attendance_reward(
    last_attendance_date: date | None,
    current_streak_days: int,
    today: date,
) -> AttendanceReward:
    if last_attendance_date == today:
        return AttendanceReward(
            streak_days=current_streak_days,
            bonus_exp=0,
            is_first_attendance_today=False,
        )

    yesterday = today - timedelta(days=1)
    streak_days = current_streak_days + 1 if last_attendance_date == yesterday else 1
    bonus_exp = 2
    if streak_days >= 7:
        bonus_exp += 10
    elif streak_days >= 3:
        bonus_exp += 5

    return AttendanceReward(
        streak_days=streak_days,
        bonus_exp=bonus_exp,
        is_first_attendance_today=True,
    )
