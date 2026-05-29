from dataclasses import dataclass
from datetime import datetime
from statistics import median


RISK_LEVELS = (
    (30, "LOW"),
    (60, "MEDIUM"),
    (80, "HIGH"),
    (100, "CRITICAL"),
)


@dataclass(frozen=True)
class AnalyticsSession:
    start_time: datetime
    end_time: datetime | None
    status: str
    total_seconds: int | None = None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _risk_level(score: float) -> str:
    for ceiling, level in RISK_LEVELS:
        if score <= ceiling:
            return level
    return "CRITICAL"


def _failure_rate(total_count: int, failed_count: int) -> float:
    if total_count == 0:
        return 0.0
    return failed_count / total_count * 100


def _session_duration_minutes(session: AnalyticsSession) -> float | None:
    if session.end_time is not None:
        seconds = (session.end_time - session.start_time).total_seconds()
    elif session.total_seconds is not None:
        seconds = session.total_seconds
    else:
        return None

    if seconds <= 0:
        return None
    return seconds / 60


def _trim_outliers(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values

    sorted_values = sorted(values)
    center = median(sorted_values)
    deviations = [abs(value - center) for value in sorted_values]
    median_deviation = median(deviations)
    if median_deviation > 0:
        # 실패 세션 표본은 작게 쌓이기 쉬워서 평균보다 중앙값 기반 필터가 덜 흔들립니다.
        trimmed = [
            value
            for value in values
            if 0.6745 * abs(value - center) / median_deviation <= 3.5
        ]
        return trimmed or values

    midpoint = len(sorted_values) // 2
    lower_half = sorted_values[:midpoint]
    upper_half = sorted_values[midpoint + (len(sorted_values) % 2) :]
    q1 = median(lower_half)
    q3 = median(upper_half)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    # 값이 한쪽에 몰려 MAD가 0이 되는 경우에는 일반적인 IQR 방식으로 한 번 더 거릅니다.
    trimmed = [value for value in values if lower_bound <= value <= upper_bound]
    return trimmed or values


def _collapse_risk_score(predicted_minute: int | None) -> float:
    if predicted_minute is None:
        return 0.0
    # 빨리 무너지는 사용자일수록 세션 초반 알림의 우선순위를 높게 잡습니다.
    if predicted_minute <= 15:
        return 90.0
    if predicted_minute <= 25:
        return 70.0
    if predicted_minute <= 40:
        return 45.0
    return 25.0


def _recommendation(risk_level: str) -> str:
    if risk_level == "CRITICAL":
        return "해당 시간대에는 10분 단위의 짧은 목표부터 시작하는 것을 추천합니다."
    if risk_level == "HIGH":
        return "공부 시작 전 목표를 작게 나누고 중간 휴식 알림을 설정해보세요."
    if risk_level == "MEDIUM":
        return "집중이 흔들리기 쉬운 구간이므로 시작 전 환경을 정리해보세요."
    return "현재 패턴은 안정적입니다. 지금의 학습 루틴을 유지해보세요."


def _day_name(day_of_week: int) -> str:
    return ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"][day_of_week]


def build_focus_analytics(
    sessions: list[AnalyticsSession],
    recent_session_limit: int = 10,
    recent_failed_limit: int = 10,
) -> dict:
    # 진행 중인 세션은 결과가 아직 확정되지 않았으므로 분석 모수에서 제외합니다.
    completed_sessions = [
        session
        for session in sessions
        if session.start_time is not None and session.status != "active"
    ]
    total_attempts = len(completed_sessions)
    failed_sessions = [session for session in completed_sessions if session.status == "failed"]
    failed_attempts = len(failed_sessions)
    baseline_failure_rate = _failure_rate(total_attempts, failed_attempts)

    recent_sessions = sorted(
        completed_sessions,
        key=lambda session: session.start_time,
        reverse=True,
    )[:recent_session_limit]
    # 최근 흐름은 사용자의 컨디션 변화가 바로 반영되도록 별도 비중을 둡니다.
    recent_failure_rate = _failure_rate(
        len(recent_sessions),
        sum(1 for session in recent_sessions if session.status == "failed"),
    )

    recent_failed_sessions = sorted(
        failed_sessions,
        key=lambda session: session.start_time,
        reverse=True,
    )[:recent_failed_limit]
    failed_durations = [
        duration
        for session in recent_failed_sessions
        if (duration := _session_duration_minutes(session)) is not None
    ]
    stable_durations = _trim_outliers(failed_durations)
    predicted_collapse_minute = (
        round(median(stable_durations)) if stable_durations else None
    )
    # 실제 붕괴 시점보다 조금 앞서 알려줘야 프론트에서 경고 카드로 쓸 수 있습니다.
    risk_start_minute = (
        max(1, round(predicted_collapse_minute * 0.8))
        if predicted_collapse_minute is not None
        else None
    )
    collapse_risk_score = _collapse_risk_score(predicted_collapse_minute)

    day_stats = {
        day: {"total": 0, "failed": 0}
        for day in range(7)
    }
    slot_stats: dict[tuple[int, int], dict[str, int]] = {}
    for session in completed_sessions:
        day_of_week = (session.start_time.weekday() + 1) % 7
        hour = session.start_time.hour
        day_stats[day_of_week]["total"] += 1
        if session.status == "failed":
            day_stats[day_of_week]["failed"] += 1

        slot_key = (day_of_week, hour)
        if slot_key not in slot_stats:
            slot_stats[slot_key] = {"total": 0, "failed": 0}
        slot_stats[slot_key]["total"] += 1
        if session.status == "failed":
            slot_stats[slot_key]["failed"] += 1

    risk_map = []
    for (day_of_week, hour), stats in sorted(slot_stats.items()):
        total_count = stats["total"]
        failed_count = stats["failed"]
        failure_rate = _failure_rate(total_count, failed_count)
        day_failure_rate = _failure_rate(
            day_stats[day_of_week]["total"],
            day_stats[day_of_week]["failed"],
        )
        # baselineDiff는 "이 시간대가 이 사용자 평균보다 얼마나 위험한가"를 보여주는 값입니다.
        baseline_diff = failure_rate - baseline_failure_rate
        baseline_boost = max(0.0, baseline_diff)
        # 프론트는 riskScore만으로도 색상 강도를 정할 수 있게 0~100 범위로 정규화합니다.
        risk_score = _clamp(
            0.30 * failure_rate
            + 0.25 * day_failure_rate
            + 0.25 * recent_failure_rate
            + 0.20 * collapse_risk_score
            + 0.20 * baseline_boost
        )
        risk_level = _risk_level(risk_score)

        if total_count < 2:
            reason = "분석 데이터가 적어 참고용 위험도입니다."
        elif baseline_diff > 0:
            reason = f"개인 평균보다 실패 위험이 {baseline_diff:.1f}%p 높은 시간대입니다."
        else:
            reason = "개인 평균 대비 안정적인 시간대입니다."

        risk_map.append(
            {
                "dayOfWeek": day_of_week,
                "hour": hour,
                "riskScore": round(risk_score, 1),
                "riskLevel": risk_level,
                "failureRate": round(failure_rate, 1),
                "baselineDiff": round(baseline_diff, 1),
                "totalAttempts": total_count,
                "failedAttempts": failed_count,
                "reason": reason,
            }
        )

    highest_risk = max(risk_map, key=lambda item: item["riskScore"], default=None)
    if highest_risk is None:
        summary = {
            "highestRiskDay": None,
            "highestRiskHour": None,
            "riskMultiplier": 0.0,
            "recommendation": "분석을 위해 공부 세션 데이터가 더 필요합니다.",
        }
    else:
        risk_multiplier = (
            highest_risk["failureRate"] / baseline_failure_rate
            if baseline_failure_rate > 0
            else 0.0
        )
        # 요약 카드는 히트맵을 보지 않아도 가장 조심할 구간을 바로 보여주기 위한 값입니다.
        summary = {
            "highestRiskDay": _day_name(highest_risk["dayOfWeek"]),
            "highestRiskHour": highest_risk["hour"],
            "riskMultiplier": round(risk_multiplier, 1),
            "recommendation": _recommendation(highest_risk["riskLevel"]),
        }

    prediction_level = _risk_level(collapse_risk_score)
    if predicted_collapse_minute is None:
        collapse_message = "집중 붕괴 예측을 위해 실패 세션 데이터가 더 필요합니다."
    else:
        collapse_message = (
            f"시작 후 {risk_start_minute}분부터 집중 이탈 위험이 높아집니다."
        )

    return {
        "riskMap": risk_map,
        "collapsePrediction": {
            "riskStartMinute": risk_start_minute,
            "predictedCollapseMinute": predicted_collapse_minute,
            "riskLevel": prediction_level,
            "message": collapse_message,
            "sampleSize": len(stable_durations),
        },
        "summary": summary,
        "metadata": {
            "totalAttempts": total_attempts,
            "failedAttempts": failed_attempts,
            "baselineFailureRate": round(baseline_failure_rate, 1),
            "recentFailureRate": round(recent_failure_rate, 1),
            "isEnoughData": total_attempts >= 5 and failed_attempts >= 1,
        },
    }
