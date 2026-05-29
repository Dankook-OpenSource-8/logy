from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.ai_video_verification import verify_study_video
from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.random_auth_schedule import (
    auth_expires_at,
    is_auth_expired,
    weighted_auth_delay_minutes,
)
from core.storage import upload_video
from db.database import SessionLocal, get_db
from db.models import AuthLog, FocusInterruption, SessionStatus, StudySession, User, UserPushToken
from schemas import (
    ActiveStudySessionResponse,
    AuthResponse,
    FocusInterruptionCreateRequest,
    FocusInterruptionResponse,
    NicknameCheckResponse,
    PushTokenRegisterRequest,
    PushTokenRegisterResponse,
    StudySessionCompleteRequest,
    StudySessionCompleteResponse,
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
