from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import get_db
from models import User
from schemas import (
    AuthResponse,
    NicknameCheckResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
)

app = FastAPI(title="Logy Backend")
BASE_DIR = Path(__file__).resolve().parent

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize(value: str) -> str:
    return value.strip()


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def api_test_page() -> FileResponse:
    return FileResponse(BASE_DIR / "api_test.html")


@app.get("/users/check-nickname", response_model=NicknameCheckResponse)
def check_nickname(nickname: str, db: Session = Depends(get_db)) -> NicknameCheckResponse:
    cleaned_nickname = _normalize(nickname)
    if not cleaned_nickname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="닉네임을 입력해주세요",
        )

    exists = db.query(User.id).filter(User.nickname == cleaned_nickname).first() is not None
    return NicknameCheckResponse(nickname=cleaned_nickname, available=not exists)


@app.post("/users/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: UserSignupRequest, db: Session = Depends(get_db)) -> User:
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


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
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


@app.get("/users/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@app.post("/auth/logout")
def logout() -> dict[str, str]:
    return {"message": "로그아웃 성공"}
