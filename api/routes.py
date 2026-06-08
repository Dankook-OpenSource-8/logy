from datetime import date, datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from core.ai_video_verification import verify_study_video
from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.random_auth_schedule import (
    auth_expires_at,
    is_auth_expired,
    weighted_auth_delay_minutes,
)
from core.focus_analytics import AnalyticsSession, build_focus_analytics
from core.rewards import (
    PET_EVOLUTION_STAGES,
    attendance_reward,
    furniture_progress_from_auth_minutes,
    next_pet_stage,
    pet_exp_from_verified_seconds,
    pet_level_from_exp,
    pet_stage_name,
)
from core.study_archive import (
    ArchiveAuthLog,
    ArchiveSession,
    build_daily_archive,
    build_monthly_archive,
    build_weekly_archive,
)
from core.storage import upload_video
from db.database import SessionLocal, get_db
from db.models import (
    AuthLog,
    FurnitureItem,
    FurniturePiece,
    FurniturePlacement,
    FocusInterruption,
    GroupMember,
    GroupPokeLog,
    RewardLedger,
    SessionStatus,
    StudyGroup,
    StudySession,
    StudySessionRest,
    User,
    UserFurniturePieceProgress,
    UserNotificationSetting,
    UserPet,
    UserPushToken,
)
from schemas import (
    ActiveStudySessionResponse,
    AuthResponse,
    FocusInterruptionCreateRequest,
    FocusInterruptionResponse,

    GroupCreateRequest,
    GroupInviteResponse,
    GroupJoinRequest,
    GroupJoinResponse,
    GroupMembersResponse,
    GroupMemberResponse,
    GroupMemberStatusUpdateRequest,
    GroupPokeCreateRequest,
    GroupPokeResponse,
    GroupResponse,
    FocusAnalyticsResponse,

    NicknameCheckResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    PushTokenRegisterRequest,
    PushTokenRegisterResponse,
    FurniturePlacementRequest,
    FurniturePlacementResponse,
    RewardSettlementResponse,
    RewardStateResponse,
    StudyArchiveDayResponse,
    StudyArchivePeriodResponse,
    StudySessionCompleteRequest,
    StudySessionCompleteResponse,
    StudySessionRestEndResponse,
    StudySessionRestStartResponse,
    StudySessionRestStatusResponse,
    StudySessionResponse,
    StudySessionStartRequest,
    StudySessionStartResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
    VideoVerificationRequest,
    VideoVerificationResponse,
    VideoVerificationResultResponse,
    VideoUploadResponse,
)

router = APIRouter()

ONLINE_STATUSES = {"online", "offline"}
STUDY_STATUSES = {"idle", "studying", "paused", "verifying", "failed", "completed"}
GROUP_VISIBILITIES = {"public", "private"}
REST_DAILY_MAX_COUNT = 2
REST_DAILY_MAX_SECONDS = 15 * 60
DEFAULT_FURNITURE_CODE = "desk"
DEFAULT_FURNITURE_PIECES = [
    ("leg_1", "책상 다리 1", 1),
    ("leg_2", "책상 다리 2", 2),
    ("leg_3", "책상 다리 3", 3),
    ("leg_4", "책상 다리 4", 4),
    ("top", "책상 상판", 5),
]


def _normalize(value: str) -> str:
    # 사용자 입력 양끝 공백을 제거합니다.
    return value.strip()


def _is_duplicate_nickname_error(error: IntegrityError) -> bool:
    # DB unique 제약조건 중 닉네임 중복으로 발생한 에러인지 확인합니다.
    original_error = error.orig
    sqlstate = getattr(original_error, "pgcode", None) or getattr(original_error, "sqlstate", None)
    error_message = str(original_error).lower()

    if sqlstate == "23505":
        return "nickname" in error_message or "users_nickname" in error_message

    return "unique" in error_message and "nickname" in error_message


def _notification_weekdays_to_list(value: str | None) -> list[int]:
    if not value:
        return []

    weekdays = []
    for item in value.split(","):
        item = item.strip()
        if item.isdigit():
            weekday = int(item)
            if 0 <= weekday <= 6 and weekday not in weekdays:
                weekdays.append(weekday)
    return weekdays


def _notification_weekdays_to_db(weekdays: list[int]) -> str:
    normalized_weekdays = sorted(set(weekdays))
    if any(weekday < 0 or weekday > 6 for weekday in normalized_weekdays):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="반복 요일은 0부터 6 사이의 숫자만 입력할 수 있습니다",
        )
    return ",".join(str(weekday) for weekday in normalized_weekdays)


def _get_or_create_notification_setting(db: Session, user: User) -> UserNotificationSetting:
    setting = (
        db.query(UserNotificationSetting)
        .filter(UserNotificationSetting.user_id == user.id)
        .first()
    )
    if setting is not None:
        return setting

    setting = UserNotificationSetting(user_id=user.id)
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def _notification_settings_response(
    setting: UserNotificationSetting,
    message: str | None = None,
) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        message=message,
        allNotificationsEnabled=setting.all_notifications_enabled,
        randomAuthEnabled=setting.random_auth_enabled,
        groupEnabled=setting.group_enabled,
        rewardEnabled=setting.reward_enabled,
        quietHoursEnabled=setting.quiet_hours_enabled,
        quietStartTime=setting.quiet_start_time,
        quietEndTime=setting.quiet_end_time,
        quietWeekdays=_notification_weekdays_to_list(setting.quiet_weekdays),
        createdAt=setting.created_at,
        updatedAt=setting.updated_at,
    )


def _study_session_response(study_session: StudySession) -> StudySessionResponse:
    return StudySessionResponse(
        id=study_session.id,
        subject=study_session.subject,
        goal_note=study_session.goal_note,
        start_time=study_session.start_time,
        end_time=study_session.end_time,
        total_seconds=study_session.total_seconds,
        status=study_session.status.value,
        period_minutes=study_session.period_minutes,
        next_auth_time=study_session.next_auth_time,
        auth_expires_at=auth_expires_at(study_session.next_auth_time)
        if study_session.next_auth_time
        else None,
        is_paused=study_session.is_paused,
        last_paused_at=study_session.last_paused_at,
    )


def _video_extension(content_type: str, filename: str | None) -> str:
    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    extensions_by_content_type = {
        "video/webm": ".webm",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-m4v": ".m4v",
    }
    if normalized_content_type in extensions_by_content_type:
        return extensions_by_content_type[normalized_content_type]

    if filename and "." in filename:
        extension = filename.rsplit(".", 1)[-1].lower()
        if extension in {"webm", "mp4", "mov", "m4v"}:
            return f".{extension}"

    return ".mp4"


def _verification_result_response(auth_log: AuthLog) -> VideoVerificationResultResponse:
    return VideoVerificationResultResponse(
        auth_log_id=auth_log.id,
        study_session_id=auth_log.study_session_id,
        status=auth_log.status,
        video_url=auth_log.video_url,
        verification_score=auth_log.verification_score,
        verification_reason=auth_log.verification_reason,
        scene_score=auth_log.scene_score,
        text_score=auth_log.text_score,
        quality_score=auth_log.quality_score,
        forbidden_penalty=auth_log.forbidden_penalty,
        representative_frame_path=auth_log.representative_frame_path,
        created_at=auth_log.created_at,
        verified_at=auth_log.verified_at,
    )


def _generate_invite_code(db: Session) -> str:
    for _ in range(10):
        invite_code = secrets.token_hex(4).upper()
        exists = db.query(StudyGroup.id).filter(StudyGroup.invite_code == invite_code).first()
        if exists is None:
            return invite_code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="그룹 초대 코드를 생성하지 못했습니다",
    )


def _get_group_member_or_404(
    db: Session,
    group_id: int,
    user_id,
) -> GroupMember:
    member = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="그룹 멤버가 아닙니다",
        )
    return member


def _group_total_study_seconds(db: Session, group_id: int) -> int:
    total = (
        db.query(func.coalesce(func.sum(StudySession.total_seconds), 0))
        .join(GroupMember, GroupMember.user_id == StudySession.user_id)
        .filter(
            GroupMember.group_id == group_id,
            StudySession.status == SessionStatus.completed,
        )
        .scalar()
    )
    return int(total or 0)


def _user_total_study_seconds(db: Session, user_id) -> int:
    total = (
        db.query(func.coalesce(func.sum(StudySession.total_seconds), 0))
        .filter(
            StudySession.user_id == user_id,
            StudySession.status == SessionStatus.completed,
        )
        .scalar()
    )
    return int(total or 0)


def _group_response(db: Session, group: StudyGroup) -> GroupResponse:
    member_count = (
        db.query(func.count(GroupMember.id))
        .filter(GroupMember.group_id == group.id)
        .scalar()
    )
    return GroupResponse(
        id=group.id,
        name=group.name,
        visibility=group.visibility,
        invite_code=group.invite_code,
        owner_user_id=group.owner_user_id,
        member_count=int(member_count or 0),
        group_total_study_seconds=_group_total_study_seconds(db, group.id),
        created_at=group.created_at,
    )


def _study_session_or_404(db: Session, study_session_id: int, user_id) -> StudySession:
    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == study_session_id,
            StudySession.user_id == user_id,
        )
        .first()
    )
    if study_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공부 세션을 찾을 수 없습니다",
        )
    return study_session


def _today_rest_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def _daily_rest_logs(db: Session, user_id, now: datetime) -> list[StudySessionRest]:
    day_start, day_end = _today_rest_bounds(now)
    return (
        db.query(StudySessionRest)
        .filter(
            StudySessionRest.user_id == user_id,
            StudySessionRest.started_at >= day_start,
            StudySessionRest.started_at < day_end,
        )
        .all()
    )


def _active_rest(db: Session, study_session_id: int) -> StudySessionRest | None:
    return (
        db.query(StudySessionRest)
        .filter(
            StudySessionRest.study_session_id == study_session_id,
            StudySessionRest.ended_at.is_(None),
        )
        .order_by(StudySessionRest.started_at.desc())
        .first()
    )


def _rest_status_response(
    db: Session,
    study_session: StudySession,
    now: datetime,
    **extra,
) -> dict:
    rest_logs = _daily_rest_logs(db, study_session.user_id, now)
    active_rest = _active_rest(db, study_session.id)
    used_seconds = sum(max(rest.duration_seconds or 0, 0) for rest in rest_logs)
    if active_rest is not None:
        used_seconds += max(int((now - active_rest.started_at).total_seconds()), 0)

    rest_count = len(rest_logs)
    return {
        "study_session_id": study_session.id,
        "is_paused": study_session.is_paused,
        "daily_rest_count": rest_count,
        "daily_rest_seconds": min(used_seconds, REST_DAILY_MAX_SECONDS),
        "remaining_rest_count": max(REST_DAILY_MAX_COUNT - rest_count, 0),
        "remaining_rest_seconds": max(REST_DAILY_MAX_SECONDS - used_seconds, 0),
        "active_rest_id": active_rest.id if active_rest else None,
        "active_rest_started_at": active_rest.started_at if active_rest else None,
        **extra,
    }


def _archive_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _archive_date_bounds(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date, datetime, datetime]:
    range_end = end_date or datetime.now(timezone.utc).date()
    range_start = start_date or (range_end - timedelta(days=29))
    if range_start > range_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date는 end_date보다 늦을 수 없습니다",
        )

    start_at = datetime.combine(range_start, datetime.min.time(), tzinfo=timezone.utc)
    end_at = datetime.combine(range_end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return range_start, range_end, start_at, end_at


def _archive_session_from_model(study_session: StudySession) -> ArchiveSession:
    return ArchiveSession(
        study_session_id=study_session.id,
        subject=study_session.subject,
        goal_note=study_session.goal_note,
        start_time=study_session.start_time,
        end_time=study_session.end_time,
        total_seconds=study_session.total_seconds or 0,
        status=_archive_value(study_session.status),
        auth_logs=[
            ArchiveAuthLog(
                auth_log_id=auth_log.id,
                status=_archive_value(auth_log.status),
                video_url=auth_log.video_url,
                thumbnail_url=auth_log.thumbnail_url,
                verification_score=auth_log.verification_score,
                verification_reason=auth_log.verification_reason,
                created_at=auth_log.created_at,
                verified_at=auth_log.verified_at,
            )
            for auth_log in study_session.auth_logs
        ],
    )


def _load_archive_days(
    db: Session,
    user_id,
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date, list[dict]]:
    range_start, range_end, start_at, end_at = _archive_date_bounds(start_date, end_date)
    sessions = (
        db.query(StudySession)
        .options(selectinload(StudySession.auth_logs))
        .filter(
            StudySession.user_id == user_id,
            StudySession.start_time >= start_at,
            StudySession.start_time < end_at,
        )
        .order_by(StudySession.start_time.desc())
        .all()
    )
    return range_start, range_end, build_daily_archive(
        [_archive_session_from_model(session) for session in sessions if session.start_time is not None]
    )


def _empty_archive_day(archive_date: date) -> dict:
    return {
        "date": archive_date,
        "totalSeconds": 0,
        "sessionCount": 0,
        "completedCount": 0,
        "failedCount": 0,
        "authSuccessCount": 0,
        "authFailedCount": 0,
        "authPendingCount": 0,
        "authTimeoutCount": 0,
        "sessions": [],
    }


def _get_or_create_user_pet(db: Session, user: User) -> UserPet:
    pet = db.query(UserPet).filter(UserPet.user_id == user.id).first()
    if pet is None:
        pet = UserPet(user_id=user.id)
        db.add(pet)
        db.flush()
    return pet


def _pet_response(pet: UserPet) -> dict:
    next_stage = next_pet_stage(pet.total_exp)
    return {
        "petId": pet.id,
        "name": pet.name,
        "level": pet.level,
        "stageName": pet_stage_name(pet.level),
        "totalExp": pet.total_exp,
        "nextLevel": next_stage,
        "expToNextLevel": max((next_stage or {}).get("requiredExp", pet.total_exp) - pet.total_exp, 0),
        "stages": PET_EVOLUTION_STAGES,
    }


def _get_or_create_default_furniture_catalog(db: Session) -> FurnitureItem:
    furniture_item = (
        db.query(FurnitureItem)
        .filter(FurnitureItem.code == DEFAULT_FURNITURE_CODE)
        .first()
    )
    if furniture_item is None:
        furniture_item = FurnitureItem(
            code=DEFAULT_FURNITURE_CODE,
            name="책상",
            total_piece_count=len(DEFAULT_FURNITURE_PIECES),
        )
        db.add(furniture_item)
        db.flush()

    existing_codes = {piece.code for piece in furniture_item.pieces}
    for code, name, sort_order in DEFAULT_FURNITURE_PIECES:
        if code not in existing_codes:
            db.add(
                FurniturePiece(
                    furniture_item_id=furniture_item.id,
                    code=code,
                    name=name,
                    sort_order=sort_order,
                )
            )
    db.flush()
    db.refresh(furniture_item)
    return furniture_item


def _piece_progress_by_id(db: Session, user_id, pieces: list[FurniturePiece]) -> dict[int, UserFurniturePieceProgress]:
    progress_rows = (
        db.query(UserFurniturePieceProgress)
        .filter(
            UserFurniturePieceProgress.user_id == user_id,
            UserFurniturePieceProgress.furniture_piece_id.in_([piece.id for piece in pieces]),
        )
        .all()
    )
    progress_by_piece_id = {progress.furniture_piece_id: progress for progress in progress_rows}
    for piece in pieces:
        if piece.id not in progress_by_piece_id:
            progress = UserFurniturePieceProgress(
                user_id=user_id,
                furniture_piece_id=piece.id,
            )
            db.add(progress)
            db.flush()
            progress_by_piece_id[piece.id] = progress
    return progress_by_piece_id


def _furniture_state(db: Session, user_id) -> list[dict]:
    furniture_items = db.query(FurnitureItem).order_by(FurnitureItem.id.asc()).all()
    if not furniture_items:
        furniture_items = [_get_or_create_default_furniture_catalog(db)]

    state = []
    for furniture_item in furniture_items:
        pieces = sorted(furniture_item.pieces, key=lambda piece: piece.sort_order)
        progress_by_piece_id = _piece_progress_by_id(db, user_id, pieces)
        piece_payloads = [
            {
                "furniturePieceId": piece.id,
                "code": piece.code,
                "name": piece.name,
                "progressPercent": progress_by_piece_id[piece.id].progress_percent,
                "completedCount": progress_by_piece_id[piece.id].completed_count,
            }
            for piece in pieces
        ]
        completed_piece_count = sum(1 for piece in piece_payloads if piece["completedCount"] > 0)
        state.append(
            {
                "furnitureItemId": furniture_item.id,
                "code": furniture_item.code,
                "name": furniture_item.name,
                "totalPieceCount": furniture_item.total_piece_count,
                "completedPieceCount": completed_piece_count,
                "isCompleted": completed_piece_count >= furniture_item.total_piece_count,
                "pieces": piece_payloads,
            }
        )
    return state


def _placement_response(placement: FurniturePlacement) -> dict:
    return {
        "placementId": placement.id,
        "furnitureItemId": placement.furniture_item_id,
        "furnitureCode": placement.furniture_item.code,
        "furnitureName": placement.furniture_item.name,
        "placed": placement.placed,
        "positionX": placement.position_x,
        "positionY": placement.position_y,
    }


def _reward_state_response(db: Session, user: User) -> dict:
    pet = _get_or_create_user_pet(db, user)
    furniture = _furniture_state(db, user.id)
    placements = (
        db.query(FurniturePlacement)
        .options(selectinload(FurniturePlacement.furniture_item))
        .filter(FurniturePlacement.user_id == user.id)
        .order_by(FurniturePlacement.id.asc())
        .all()
    )
    return {
        "pet": _pet_response(pet),
        "furniture": furniture,
        "placements": [_placement_response(placement) for placement in placements],
    }


def _current_furniture_piece_progress(
    db: Session,
    user_id,
) -> UserFurniturePieceProgress | None:
    furniture_item = _get_or_create_default_furniture_catalog(db)
    pieces = sorted(furniture_item.pieces, key=lambda piece: piece.sort_order)
    progress_by_piece_id = _piece_progress_by_id(db, user_id, pieces)
    for piece in pieces:
        progress = progress_by_piece_id[piece.id]
        if progress.completed_count == 0:
            return progress
    return None


def _ensure_completed_furniture_placement(db: Session, user_id) -> None:
    furniture_item = _get_or_create_default_furniture_catalog(db)
    pieces = sorted(furniture_item.pieces, key=lambda piece: piece.sort_order)
    progress_by_piece_id = _piece_progress_by_id(db, user_id, pieces)
    if any(progress_by_piece_id[piece.id].completed_count == 0 for piece in pieces):
        return

    existing_placement = (
        db.query(FurniturePlacement)
        .filter(
            FurniturePlacement.user_id == user_id,
            FurniturePlacement.furniture_item_id == furniture_item.id,
        )
        .first()
    )
    if existing_placement is None:
        db.add(
            FurniturePlacement(
                user_id=user_id,
                furniture_item_id=furniture_item.id,
                placed=False,
            )
        )


def _verified_seconds_for_auth(
    db: Session,
    auth_log: AuthLog,
    study_session: StudySession,
) -> int:
    if auth_log.verified_at is None or study_session.start_time is None:
        return 0

    previous_success = (
        db.query(AuthLog)
        .filter(
            AuthLog.study_session_id == study_session.id,
            AuthLog.id != auth_log.id,
            AuthLog.status == "성공",
            AuthLog.verified_at.isnot(None),
            AuthLog.verified_at < auth_log.verified_at,
        )
        .order_by(AuthLog.verified_at.desc())
        .first()
    )
    started_at = previous_success.verified_at if previous_success else study_session.start_time
    return max(int((auth_log.verified_at - started_at).total_seconds()), 0)


def _settle_success_reward(
    db: Session,
    auth_log: AuthLog,
    study_session: StudySession,
    user: User,
) -> RewardLedger:
    existing_log = db.query(RewardLedger).filter(RewardLedger.auth_log_id == auth_log.id).first()
    if existing_log is not None:
        return existing_log
    if auth_log.status != "성공":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="성공한 인증만 보상을 정산할 수 있습니다",
        )

    verified_seconds = _verified_seconds_for_auth(db, auth_log, study_session)
    pet_exp = pet_exp_from_verified_seconds(verified_seconds)
    attendance = attendance_reward(
        user.last_attendance_date,
        user.streak_days or 0,
        auth_log.verified_at.date() if auth_log.verified_at else datetime.now(timezone.utc).date(),
    )

    pet = _get_or_create_user_pet(db, user)
    pet.total_exp += pet_exp + attendance.bonus_exp
    pet.level = pet_level_from_exp(pet.total_exp)

    if attendance.is_first_attendance_today:
        user.streak_days = attendance.streak_days
        user.last_attendance_date = auth_log.verified_at.date()

    auth_minutes = verified_seconds // 60
    progress_percent = furniture_progress_from_auth_minutes(auth_minutes)
    piece_progress = _current_furniture_piece_progress(db, user.id)
    furniture_piece_id = piece_progress.furniture_piece_id if piece_progress else None
    if piece_progress is not None:
        piece_progress.progress_percent += progress_percent
        if piece_progress.progress_percent >= 100:
            piece_progress.completed_count = 1
            piece_progress.progress_percent = 100
        _ensure_completed_furniture_placement(db, user.id)

    reward_log = RewardLedger(
        user_id=user.id,
        study_session_id=study_session.id,
        auth_log_id=auth_log.id,
        verified_seconds=verified_seconds,
        pet_exp=pet_exp,
        attendance_bonus_exp=attendance.bonus_exp,
        furniture_piece_id=furniture_piece_id,
        furniture_progress_percent=progress_percent if piece_progress is not None else 0,
    )
    db.add(reward_log)
    db.flush()
    return reward_log


def _run_video_verification(auth_log_id: int) -> None:
    db = SessionLocal()
    try:
        auth_log = db.query(AuthLog).filter(AuthLog.id == auth_log_id).first()
        if auth_log is None:
            return

        study_session = (
            db.query(StudySession)
            .filter(StudySession.id == auth_log.study_session_id)
            .first()
        )
        if study_session is None:
            auth_log.status = "실패"
            auth_log.error_message = "공부 세션을 찾을 수 없습니다"
            auth_log.verified_at = datetime.now(timezone.utc)
            db.commit()
            return

        try:
            result = verify_study_video(auth_log.video_url, study_session.subject)
        except Exception as error:
            auth_log.status = "시간초과"
            auth_log.error_message = str(error)
            auth_log.verification_reason = "AI 영상 검증 중 오류가 발생했습니다."
            auth_log.verified_at = datetime.now(timezone.utc)
            db.commit()
            return

        verified_at = datetime.now(timezone.utc)
        auth_log.status = result.status
        auth_log.verification_score = result.total_score
        auth_log.verification_reason = result.reason
        auth_log.scene_score = result.scene_score
        auth_log.text_score = result.text_score
        auth_log.quality_score = result.quality_score
        auth_log.forbidden_penalty = result.forbidden_penalty
        auth_log.representative_frame_path = result.representative_frame_path
        auth_log.verified_at = verified_at
        auth_log.error_message = None if result.approved else result.reason

        if result.approved:
            user = db.query(User).filter(User.id == auth_log.user_id).first()
            if user is not None:
                _settle_success_reward(db, auth_log, study_session, user)
            auth_delay_minutes = weighted_auth_delay_minutes()
            study_session.period_minutes = auth_delay_minutes
            study_session.next_auth_time = verified_at + timedelta(minutes=auth_delay_minutes)
        else:
            study_session.status = SessionStatus.failed
            study_session.end_time = verified_at

        db.commit()
    finally:
        db.close()


@router.get("/health")
def health_check() -> dict[str, str]:
    # 서버가 정상 실행 중인지 확인합니다.
    return {"status": "ok"}


@router.get("/users/check-nickname", response_model=NicknameCheckResponse)
def check_nickname(nickname: str, db: Session = Depends(get_db)) -> NicknameCheckResponse:
    # 닉네임 사용 가능 여부를 조회합니다.
    cleaned_nickname = _normalize(nickname)
    if not cleaned_nickname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="닉네임을 입력해주세요",
        )

    exists = db.query(User.id).filter(User.nickname == cleaned_nickname).first() is not None
    return NicknameCheckResponse(nickname=cleaned_nickname, available=not exists)


@router.post("/users/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: UserSignupRequest, db: Session = Depends(get_db)) -> User:
    # 신규 사용자를 생성하고 비밀번호는 해시로 저장합니다.
    real_name = _normalize(payload.real_name)
    nickname = _normalize(payload.nickname)
    password = payload.password.strip()

    if not real_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="본명을 입력해주세요",
        )
    if not nickname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="닉네임을 입력해주세요",
        )
    if len(password) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호는 4자 이상 입력해주세요",
        )

    duplicated_user = db.query(User.id).filter(User.nickname == nickname).first()
    if duplicated_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="중복된 닉네임입니다",
        )

    user = User(
        real_name=real_name,
        nickname=nickname,
        password=hash_password(password),
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _is_duplicate_nickname_error(error):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="중복된 닉네임입니다",
            ) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="회원가입 처리 중 데이터베이스 오류가 발생했습니다",
        ) from None

    db.refresh(user)
    return user


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    # 닉네임과 비밀번호를 검증하고 access token을 발급합니다.
    nickname = _normalize(payload.nickname)
    password = payload.password.strip()
    if not nickname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="닉네임을 입력해주세요",
        )
    if not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호를 입력해주세요",
        )

    user = db.query(User).filter(User.nickname == nickname).first()
    if user is None or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="닉네임 또는 비밀번호가 올바르지 않습니다",
        )

    return AuthResponse(
        message="로그인 성공",
        access_token=create_access_token(user.id),
        user=user,
    )


@router.get("/users/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    # 토큰으로 인증된 현재 사용자 정보를 반환합니다.
    return current_user


@router.post("/auth/logout")
def logout() -> dict[str, str]:
    # 클라이언트가 저장한 토큰을 지우도록 성공 응답만 반환합니다.
    return {"message": "로그아웃 성공"}


@router.post("/users/push-token", response_model=PushTokenRegisterResponse)
def register_push_token(
    payload: PushTokenRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PushTokenRegisterResponse:
    # Expo 앱 푸시 토큰을 저장해 인증 알림과 팀원 알림에 사용합니다.
    expo_push_token = payload.expo_push_token.strip()
    if not expo_push_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="푸시 토큰을 입력해주세요",
        )

    push_token = (
        db.query(UserPushToken)
        .filter(UserPushToken.expo_push_token == expo_push_token)
        .first()
    )
    if push_token is None:
        push_token = UserPushToken(
            user_id=current_user.id,
            expo_push_token=expo_push_token,
        )
        db.add(push_token)
    else:
        push_token.user_id = current_user.id

    push_token.platform = payload.platform.strip() if payload.platform else None
    push_token.is_active = True

    try:
        db.commit()
        db.refresh(push_token)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="푸시 토큰 저장 중 중복 오류가 발생했습니다",
        ) from None

    return PushTokenRegisterResponse(
        message="푸시 토큰 저장",
        push_token_id=push_token.id,
    )


@router.get("/users/notification-settings", response_model=NotificationSettingsResponse)
def get_notification_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationSettingsResponse:
    setting = _get_or_create_notification_setting(db, current_user)
    return _notification_settings_response(setting)


@router.put("/users/notification-settings", response_model=NotificationSettingsResponse)
def update_notification_settings(
    payload: NotificationSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationSettingsResponse:
    setting = _get_or_create_notification_setting(db, current_user)
    if payload.quiet_hours_enabled and (
        payload.quiet_start_time is None or payload.quiet_end_time is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="방해 금지 시간을 사용할 경우 시작 시간과 종료 시간을 모두 입력해주세요",
        )

    setting.all_notifications_enabled = payload.all_notifications_enabled
    setting.random_auth_enabled = payload.random_auth_enabled
    setting.group_enabled = payload.group_enabled
    setting.reward_enabled = payload.reward_enabled
    setting.quiet_hours_enabled = payload.quiet_hours_enabled
    setting.quiet_start_time = payload.quiet_start_time
    setting.quiet_end_time = payload.quiet_end_time
    setting.quiet_weekdays = _notification_weekdays_to_db(payload.quiet_weekdays)

    try:
        db.commit()
        db.refresh(setting)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="알림 설정을 저장하지 못했습니다",
        ) from None

    return _notification_settings_response(setting, "알림 설정 저장")


@router.get("/rewards/me", response_model=RewardStateResponse)
def get_my_reward_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # 농장 화면 진입 시 펫 성장과 가구 진행도를 한 번에 복구합니다.
    return _reward_state_response(db, current_user)


@router.post("/rewards/settle/{auth_log_id}", response_model=RewardSettlementResponse)
def settle_reward_by_auth_log(
    auth_log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # 비동기 AI 검증이 이미 성공한 로그에 대해 보상을 수동 재정산할 때 사용합니다.
    auth_log = (
        db.query(AuthLog)
        .filter(
            AuthLog.id == auth_log_id,
            AuthLog.user_id == current_user.id,
        )
        .first()
    )
    if auth_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="인증 로그를 찾을 수 없습니다",
        )
    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == auth_log.study_session_id,
            StudySession.user_id == current_user.id,
        )
        .first()
    )
    if study_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공부 세션을 찾을 수 없습니다",
        )

    reward_log = _settle_success_reward(db, auth_log, study_session, current_user)
    db.commit()
    db.refresh(reward_log)
    state = _reward_state_response(db, current_user)
    return {
        "message": "보상 정산 완료",
        "rewardLogId": reward_log.id,
        "verifiedSeconds": reward_log.verified_seconds,
        "petExp": reward_log.pet_exp,
        "attendanceBonusExp": reward_log.attendance_bonus_exp,
        "streakDays": current_user.streak_days,
        "furnitureProgressPercent": reward_log.furniture_progress_percent,
        "furniturePieceId": reward_log.furniture_piece_id,
        "pet": state["pet"],
        "furniture": state["furniture"],
    }


@router.post("/furniture/placements", response_model=FurniturePlacementResponse)
def upsert_furniture_placement(
    payload: FurniturePlacementRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    furniture_item = (
        db.query(FurnitureItem)
        .filter(FurnitureItem.id == payload.furniture_item_id)
        .first()
    )
    if furniture_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="가구를 찾을 수 없습니다",
        )

    furniture_state = _furniture_state(db, current_user.id)
    matching_item = next(
        (item for item in furniture_state if item["furnitureItemId"] == furniture_item.id),
        None,
    )
    if matching_item is None or not matching_item["isCompleted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="완성된 가구만 배치할 수 있습니다",
        )

    placement = (
        db.query(FurniturePlacement)
        .filter(
            FurniturePlacement.user_id == current_user.id,
            FurniturePlacement.furniture_item_id == furniture_item.id,
        )
        .first()
    )
    if placement is None:
        placement = FurniturePlacement(
            user_id=current_user.id,
            furniture_item_id=furniture_item.id,
        )
        db.add(placement)

    placement.placed = payload.placed
    placement.position_x = payload.position_x
    placement.position_y = payload.position_y
    db.commit()
    db.refresh(placement)
    return _placement_response(placement)


@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupResponse:
    group_name = payload.name.strip()
    visibility = payload.visibility.strip().lower()
    if not group_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="그룹 이름을 입력해주세요",
        )
    if visibility not in GROUP_VISIBILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="그룹 공개 범위 값이 올바르지 않습니다",
        )

    group = StudyGroup(
        owner_user_id=current_user.id,
        name=group_name,
        invite_code=_generate_invite_code(db),
        visibility=visibility,
    )
    db.add(group)
    db.flush()

    db.add(
        GroupMember(
            group_id=group.id,
            user_id=current_user.id,
            role="owner",
            online_status="online",
            study_status="idle",
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.refresh(group)
    return _group_response(db, group)


@router.get("/groups/search", response_model=list[GroupResponse])
def search_public_groups(
    query: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GroupResponse]:
    groups_query = (
        db.query(StudyGroup)
        .filter(StudyGroup.visibility == "public")
        .order_by(StudyGroup.created_at.desc())
    )
    if query and query.strip():
        groups_query = groups_query.filter(StudyGroup.name.ilike(f"%{query.strip()}%"))

    groups = groups_query.limit(30).all()
    return [_group_response(db, group) for group in groups]


@router.get("/groups", response_model=list[GroupResponse])
def list_my_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GroupResponse]:
    groups = (
        db.query(StudyGroup)
        .join(GroupMember, GroupMember.group_id == StudyGroup.id)
        .filter(GroupMember.user_id == current_user.id)
        .order_by(StudyGroup.created_at.desc())
        .all()
    )
    return [_group_response(db, group) for group in groups]


@router.post("/groups/{group_id}/invites", response_model=GroupInviteResponse)
def get_group_invite(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupInviteResponse:
    _get_group_member_or_404(db, group_id, current_user.id)
    group = db.query(StudyGroup).filter(StudyGroup.id == group_id).first()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="그룹을 찾을 수 없습니다",
        )
    return GroupInviteResponse(group_id=group.id, invite_code=group.invite_code)


@router.post("/groups/join", response_model=GroupJoinResponse)
def join_group(
    payload: GroupJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupJoinResponse:
    invite_code = payload.invite_code.strip().upper()
    group = db.query(StudyGroup).filter(StudyGroup.invite_code == invite_code).first()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="유효하지 않은 초대 코드입니다",
        )

    existing_member = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group.id,
            GroupMember.user_id == current_user.id,
        )
        .first()
    )
    if existing_member is None:
        db.add(
            GroupMember(
                group_id=group.id,
                user_id=current_user.id,
                role="member",
                online_status="online",
                study_status="idle",
                last_seen_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    return GroupJoinResponse(
        message="그룹 참여 완료",
        group=_group_response(db, group),
    )


@router.get("/groups/{group_id}/members", response_model=GroupMembersResponse)
def get_group_members(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupMembersResponse:
    _get_group_member_or_404(db, group_id, current_user.id)
    group = db.query(StudyGroup).filter(StudyGroup.id == group_id).first()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="그룹을 찾을 수 없습니다",
        )

    members = (
        db.query(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
        .all()
    )

    return GroupMembersResponse(
        group_id=group.id,
        group_name=group.name,
        group_total_study_seconds=_group_total_study_seconds(db, group.id),
        members=[
            GroupMemberResponse(
                user_id=user.id,
                nickname=user.nickname,
                role=member.role,
                online_status=member.online_status,
                study_status=member.study_status,
                active_study_session_id=member.active_study_session_id,
                last_seen_at=member.last_seen_at,
                total_study_seconds=_user_total_study_seconds(db, user.id),
            )
            for member, user in members
        ],
    )


@router.put("/groups/{group_id}/presence", response_model=GroupMemberResponse)
def update_group_presence(
    group_id: int,
    payload: GroupMemberStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupMemberResponse:
    member = _get_group_member_or_404(db, group_id, current_user.id)
    online_status = payload.online_status.strip().lower()
    study_status = payload.study_status.strip().lower()
    if online_status not in ONLINE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="온라인 상태 값이 올바르지 않습니다",
        )
    if study_status not in STUDY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="공부 상태 값이 올바르지 않습니다",
        )

    if payload.active_study_session_id is not None:
        active_session = (
            db.query(StudySession.id)
            .filter(
                StudySession.id == payload.active_study_session_id,
                StudySession.user_id == current_user.id,
            )
            .first()
        )
        if active_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="활성 공부 세션을 찾을 수 없습니다",
            )

    now = datetime.now(timezone.utc)
    member.online_status = online_status
    member.study_status = study_status
    member.active_study_session_id = payload.active_study_session_id
    member.last_seen_at = now
    member.updated_at = now
    db.commit()
    db.refresh(member)

    return GroupMemberResponse(
        user_id=current_user.id,
        nickname=current_user.nickname,
        role=member.role,
        online_status=member.online_status,
        study_status=member.study_status,
        active_study_session_id=member.active_study_session_id,
        last_seen_at=member.last_seen_at,
        total_study_seconds=_user_total_study_seconds(db, current_user.id),
    )


@router.post("/groups/{group_id}/pokes", response_model=GroupPokeResponse, status_code=status.HTTP_201_CREATED)
def create_group_poke(
    group_id: int,
    payload: GroupPokeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupPokeResponse:
    _get_group_member_or_404(db, group_id, current_user.id)
    target_member = _get_group_member_or_404(db, group_id, payload.target_user_id)
    if target_member.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="자기 자신은 콕 찌를 수 없습니다",
        )

    poke = GroupPokeLog(
        group_id=group_id,
        sender_user_id=current_user.id,
        target_user_id=target_member.user_id,
        message=payload.message.strip() if payload.message else None,
    )
    db.add(poke)
    db.commit()
    db.refresh(poke)

    return GroupPokeResponse(
        message="콕 찌르기 기록 완료",
        poke_id=poke.id,
        group_id=group_id,
        sender_user_id=current_user.id,
        target_user_id=target_member.user_id,
        created_at=poke.created_at,
    )


@router.post("/study-sessions/start", response_model=StudySessionStartResponse)
def start_study_session(
    payload: StudySessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudySessionStartResponse:
    # 공부 시작 시 DB 서버가 찍은 start_time을 기준으로 세션 row를 먼저 확정합니다.
    auth_delay_minutes = weighted_auth_delay_minutes()
    study_session = StudySession(
        user_id=current_user.id,
        subject=payload.subject.strip() if payload.subject else None,
        goal_note=payload.goal_note.strip() if payload.goal_note else None,
        period_minutes=auth_delay_minutes,
    )
    db.add(study_session)

    try:
        db.flush()
        db.refresh(study_session)
        if study_session.start_time is None:
            raise RuntimeError("study session start_time was not generated")

        next_auth_time = study_session.start_time + timedelta(minutes=auth_delay_minutes)
        study_session.next_auth_time = next_auth_time
        db.commit()
        db.refresh(study_session)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="공부 세션 시작 시각을 기록하지 못했습니다",
        ) from None

    return StudySessionStartResponse(
        message="공부 세션 시작",
        study_session_id=study_session.id,
        start_time=study_session.start_time,
        next_auth_time=study_session.next_auth_time,
        auth_expires_at=auth_expires_at(study_session.next_auth_time),
    )


@router.get("/study-sessions/active", response_model=ActiveStudySessionResponse)
def get_active_study_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActiveStudySessionResponse:
    # 앱 재실행/화면 복귀 시 현재 진행 중인 세션을 복구합니다.
    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.user_id == current_user.id,
            StudySession.status == SessionStatus.active,
        )
        .order_by(StudySession.start_time.desc())
        .first()
    )

    return ActiveStudySessionResponse(
        active_session=_study_session_response(study_session) if study_session else None
    )


@router.get(
    "/study-sessions/{study_session_id}/rests/status",
    response_model=StudySessionRestStatusResponse,
)
def get_study_session_rest_status(
    study_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    study_session = _study_session_or_404(db, study_session_id, current_user.id)
    return _rest_status_response(db, study_session, datetime.now(timezone.utc))


@router.post(
    "/study-sessions/{study_session_id}/rests/start",
    response_model=StudySessionRestStartResponse,
)
def start_study_session_rest(
    study_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    study_session = _study_session_or_404(db, study_session_id, current_user.id)
    if study_session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="진행 중인 공부 세션에서만 휴식할 수 있습니다",
        )
    if study_session.is_paused or _active_rest(db, study_session.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 휴식 중입니다",
        )

    now = datetime.now(timezone.utc)
    rest_status = _rest_status_response(db, study_session, now)
    if rest_status["remaining_rest_count"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="오늘 사용할 수 있는 휴식 횟수를 모두 사용했습니다",
        )
    if rest_status["remaining_rest_seconds"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="오늘 사용할 수 있는 휴식 시간이 모두 소진되었습니다",
        )

    rest_log = StudySessionRest(
        user_id=current_user.id,
        study_session_id=study_session.id,
        started_at=now,
    )
    study_session.is_paused = True
    study_session.last_paused_at = now
    db.add(rest_log)
    db.commit()
    db.refresh(rest_log)
    db.refresh(study_session)

    return _rest_status_response(
        db,
        study_session,
        now,
        message="휴식 시작",
        rest_id=rest_log.id,
    )


@router.post(
    "/study-sessions/{study_session_id}/rests/end",
    response_model=StudySessionRestEndResponse,
)
def end_study_session_rest(
    study_session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    study_session = _study_session_or_404(db, study_session_id, current_user.id)
    active_rest = _active_rest(db, study_session.id)
    if active_rest is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="진행 중인 휴식이 없습니다",
        )

    now = datetime.now(timezone.utc)
    used_before = sum(
        max(rest.duration_seconds or 0, 0)
        for rest in _daily_rest_logs(db, current_user.id, now)
        if rest.id != active_rest.id
    )
    rest_seconds = max(int((now - active_rest.started_at).total_seconds()), 0)
    rest_seconds = min(rest_seconds, max(REST_DAILY_MAX_SECONDS - used_before, 0))

    active_rest.ended_at = now
    active_rest.duration_seconds = rest_seconds
    study_session.is_paused = False
    study_session.last_paused_at = None
    db.commit()
    db.refresh(active_rest)
    db.refresh(study_session)

    return _rest_status_response(
        db,
        study_session,
        now,
        message="휴식 종료",
        rest_id=active_rest.id,
        rest_seconds=rest_seconds,
    )


@router.get("/study-archive/days", response_model=list[StudyArchiveDayResponse])
def get_study_archive_days(
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    # 캘린더와 리스트 화면에서 쓰는 날짜별 원본 아카이브입니다.
    _, _, days = _load_archive_days(db, current_user.id, start_date, end_date)
    return days


@router.get("/study-archive/days/{archive_date}", response_model=StudyArchiveDayResponse)
def get_study_archive_day(
    archive_date: date,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # 특정 날짜 상세 화면에서 세션과 인증 영상을 함께 보여줄 때 사용합니다.
    _, _, days = _load_archive_days(db, current_user.id, archive_date, archive_date)
    return days[0] if days else _empty_archive_day(archive_date)


@router.get("/study-archive/weeks", response_model=list[StudyArchivePeriodResponse])
def get_study_archive_weeks(
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _, _, days = _load_archive_days(db, current_user.id, start_date, end_date)
    return build_weekly_archive(days)


@router.get("/study-archive/months", response_model=list[StudyArchivePeriodResponse])
def get_study_archive_months(
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _, _, days = _load_archive_days(db, current_user.id, start_date, end_date)
    return build_monthly_archive(days)


@router.post(
    "/study-sessions/{study_session_id}/complete",
    response_model=StudySessionCompleteResponse,
)
def complete_study_session(
    study_session_id: int,
    payload: StudySessionCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudySessionCompleteResponse:
    # 앱에서 정상 종료한 순공 시간을 서버에 확정 저장합니다.
    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == study_session_id,
            StudySession.user_id == current_user.id,
        )
        .first()
    )
    if study_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공부 세션을 찾을 수 없습니다",
        )
    if study_session.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="진행 중인 공부 세션만 완료할 수 있습니다",
        )

    study_session.status = SessionStatus.completed
    study_session.end_time = datetime.now(timezone.utc)
    study_session.total_seconds = payload.total_seconds
    study_session.is_paused = False
    study_session.last_paused_at = None

    current_user.total_study_time = (current_user.total_study_time or 0) + payload.total_seconds

    try:
        db.commit()
        db.refresh(study_session)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="공부 세션 완료 처리에 실패했습니다",
        ) from None

    return StudySessionCompleteResponse(
        message="공부 세션 완료",
        study_session=_study_session_response(study_session),
    )


@router.post(
    "/study-sessions/{study_session_id}/focus-interruptions",
    response_model=FocusInterruptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_focus_interruption(
    study_session_id: int,
    payload: FocusInterruptionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FocusInterruptionResponse:
    # 포커스 이탈은 서버 수신 시각을 기준으로 기록해 클라이언트 시간 조작 영향을 줄입니다.
    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == study_session_id,
            StudySession.user_id == current_user.id,
        )
        .first()
    )
    if study_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공부 세션을 찾을 수 없습니다",
        )

    focus_interruption = FocusInterruption(
        user_id=current_user.id,
        study_session_id=study_session.id,
        event_type=payload.event_type.strip(),
        client_event_at=payload.client_event_at,
        grace_seconds=payload.grace_seconds,
        penalty_applied=payload.penalty_applied,
    )
    if not focus_interruption.event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이탈 이벤트 종류를 입력해주세요",
        )

    if payload.penalty_applied:
        study_session.status = SessionStatus.failed
        study_session.end_time = datetime.now(timezone.utc)

    db.add(focus_interruption)

    try:
        db.commit()
        db.refresh(focus_interruption)
        db.refresh(study_session)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이탈 로그를 저장하지 못했습니다",
        ) from None

    return FocusInterruptionResponse(
        message="이탈 로그 기록",
        focus_interruption_id=focus_interruption.id,
        study_session_id=study_session.id,
        interrupted_at=focus_interruption.interrupted_at,
        penalty_applied=focus_interruption.penalty_applied,
        session_status=study_session.status.value,
    )


@router.get("/analytics/focus-risk", response_model=FocusAnalyticsResponse)
def get_focus_risk_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # 라우터는 DB 접근까지만 맡고, 점수 계산은 core 모듈에서 같은 기준으로 처리합니다.
    study_sessions = (
        db.query(StudySession)
        .filter(StudySession.user_id == current_user.id)
        .order_by(StudySession.start_time.desc())
        .all()
    )
    analytics_sessions = [
        AnalyticsSession(
            start_time=study_session.start_time,
            end_time=study_session.end_time,
            status=study_session.status.value,
            total_seconds=study_session.total_seconds,
        )
        for study_session in study_sessions
        if study_session.start_time is not None
    ]
    return build_focus_analytics(analytics_sessions)


@router.post("/auth/video/verify", response_model=VideoVerificationResponse)
def request_video_verification(
    payload: VideoVerificationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoVerificationResponse:
    # 앱이 Supabase Storage에 직접 올린 영상 URL을 받아 AI 검증을 비동기로 시작합니다.
    video_url = payload.video_url.strip()
    if not video_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="영상 URL을 입력해주세요",
        )

    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == payload.study_session_id,
            StudySession.user_id == current_user.id,
        )
        .first()
    )
    if study_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공부 세션을 찾을 수 없습니다",
        )
    if study_session.next_auth_time is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 요청 시간이 설정되지 않았습니다",
        )

    now = datetime.now(timezone.utc)
    expires_at = auth_expires_at(study_session.next_auth_time)
    if now < study_session.next_auth_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="아직 인증 요청 시간이 아닙니다",
        )
    if is_auth_expired(now, study_session.next_auth_time):
        study_session.status = SessionStatus.failed
        study_session.end_time = now
        auth_log = AuthLog(
            user_id=current_user.id,
            study_session_id=study_session.id,
            video_url=video_url,
            status="시간초과",
            error_message="인증 제한 시간 60초를 초과했습니다.",
            verification_reason="인증 제한 시간 60초를 초과하여 실패 처리되었습니다.",
            verified_at=now,
        )
        db.add(auth_log)
        db.commit()
        db.refresh(auth_log)
        return VideoVerificationResponse(
            message="인증 제한 시간이 초과되어 실패 처리되었습니다.",
            auth_log_id=auth_log.id,
            status=auth_log.status,
            auth_expires_at=expires_at,
        )

    auth_log = AuthLog(
        user_id=current_user.id,
        study_session_id=study_session.id,
        video_url=video_url,
        status="대기",
        verification_reason="AI 영상 검증 대기 중입니다.",
    )
    db.add(auth_log)
    db.commit()
    db.refresh(auth_log)

    background_tasks.add_task(_run_video_verification, auth_log.id)

    return VideoVerificationResponse(
        message="영상 검증 요청 접수",
        auth_log_id=auth_log.id,
        status=auth_log.status,
        auth_expires_at=expires_at,
    )


@router.get(
    "/auth/video/verify/{auth_log_id}",
    response_model=VideoVerificationResultResponse,
)
def get_video_verification_result(
    auth_log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoVerificationResultResponse:
    # 프론트가 pending 이후 polling으로 AI 검증 결과를 조회할 때 사용합니다.
    auth_log = (
        db.query(AuthLog)
        .filter(
            AuthLog.id == auth_log_id,
            AuthLog.user_id == current_user.id,
        )
        .first()
    )
    if auth_log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="영상 검증 로그를 찾을 수 없습니다",
        )

    return _verification_result_response(auth_log)


@router.post("/auth/video", response_model=VideoUploadResponse)
async def upload_auth_video(
    study_session_id: int = Form(...),
    video: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoUploadResponse:
    # 4초 인증 영상을 Storage에 올리고 auth_logs에 인증 기록을 남깁니다.
    study_session = (
        db.query(StudySession)
        .filter(
            StudySession.id == study_session_id,
            StudySession.user_id == current_user.id,
        )
        .first()
    )
    if study_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공부 세션을 찾을 수 없습니다",
        )
    if study_session.next_auth_time is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 요청 시간이 설정되지 않았습니다",
        )

    now = datetime.now(timezone.utc)
    if now < study_session.next_auth_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="아직 인증 요청 시간이 아닙니다",
        )
    if is_auth_expired(now, study_session.next_auth_time):
        study_session.status = SessionStatus.failed
        study_session.end_time = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="인증 제한 시간 60초를 초과했습니다",
        )

    content_type = video.content_type or "video/mp4"
    if not content_type.startswith("video/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="영상 파일만 업로드할 수 있습니다",
        )

    file_bytes = await video.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드할 영상 파일이 비어 있습니다",
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    file_path = f"{current_user.id}_{timestamp}{_video_extension(content_type, video.filename)}"
    video_url = upload_video(file_path, file_bytes, content_type)

    return VideoUploadResponse(message="영상 업로드 완료", video_url=video_url)
