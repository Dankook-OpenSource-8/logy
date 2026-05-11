from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.storage import upload_video
from db.database import get_db
from db.models import AuthLog, StudySession, User
from schemas import (
    AuthResponse,
    NicknameCheckResponse,
    StudySessionStartRequest,
    StudySessionStartResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
    VideoUploadResponse,
)

router = APIRouter()


def _normalize(value: str) -> str:
    # 사용자 입력 양끝 공백을 제거합니다.
    return value.strip()


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
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="중복된 닉네임입니다",
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


@router.post("/study-sessions/start", response_model=StudySessionStartResponse)
def start_study_session(
    payload: StudySessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudySessionStartResponse:
    # 공부 시작 시 세션 row를 만들고 이후 영상 업로드에 쓸 id를 반환합니다.
    now = datetime.now(timezone.utc)
    next_auth_time = now + timedelta(minutes=payload.period_minutes)

    study_session = StudySession(
        user_id=current_user.id,
        subject=payload.subject.strip() if payload.subject else None,
        goal_note=payload.goal_note.strip() if payload.goal_note else None,
        start_time=now,
        period_minutes=payload.period_minutes,
        next_auth_time=next_auth_time,
    )
    db.add(study_session)
    db.commit()
    db.refresh(study_session)

    return StudySessionStartResponse(
        message="공부 세션 시작",
        study_session_id=study_session.id,
        next_auth_time=next_auth_time,
    )


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

    content_type = video.content_type or "video/webm"
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
    file_path = f"{current_user.id}_{timestamp}.webm"
    video_url = upload_video(file_path, file_bytes, content_type)

    auth_log = AuthLog(
        user_id=current_user.id,
        study_session_id=study_session.id,
        video_url=video_url,
        status="성공",
    )
    db.add(auth_log)
    db.commit()

    return VideoUploadResponse(message="인증 성공", video_url=video_url)
