from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from config import settings
from database import Base, engine, get_db
from models import User
from schemas import LocalLoginRequest, LocalSignupRequest, OnboardingRequest, TokenResponse, UserResponse

app = FastAPI(title="FreshMate API")
BASE_DIR = Path(__file__).resolve().parent


# 서버 시작 시 테이블 생성 함수
@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


# 인증 테스트 HTML 반환 함수
@app.get("/", response_class=HTMLResponse)
@app.get("/auth/kakao/test", response_class=HTMLResponse)
def kakao_test_page() -> HTMLResponse:
    return HTMLResponse((BASE_DIR / "kakao_test.html").read_text(encoding="utf-8"))


# 외부 API JSON 요청 함수
def _request_json(
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    # form 데이터 인코딩
    encoded_data = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, data=encoded_data, headers=headers or {}, method=method)

    try:
        # 외부 API 요청 후 JSON 응답 변환
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # 카카오 에러 응답 상세 전달
        error_body = exc.read().decode("utf-8")
        try:
            detail = json.loads(error_body)
        except json.JSONDecodeError:
            detail = error_body
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "카카오 서버가 오류 응답을 반환했습니다.",
                "status_code": exc.code,
                "kakao_error": detail,
            },
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "카카오 서버에 연결할 수 없습니다.",
                "reason": str(exc.reason),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "카카오 서버와 통신하는 중 오류가 발생했습니다.",
                "reason": str(exc),
            },
        ) from exc


# 카카오 redirect_uri 결정 함수
def _get_redirect_uri(redirect_uri: Optional[str]) -> str:
    uri = redirect_uri or settings.KAKAO_REDIRECT_URI
    if not uri:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KAKAO_REDIRECT_URI가 설정되어 있지 않습니다.",
        )
    return uri


# 카카오 access token 발급 요청 함수
def _exchange_kakao_token(code: str, redirect_uri: str) -> str:
    token_data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    # Client Secret 사용 시 함께 전송
    if settings.KAKAO_CLIENT_SECRET:
        token_data["client_secret"] = settings.KAKAO_CLIENT_SECRET

    token_response = _request_json(
        "https://kauth.kakao.com/oauth/token",
        method="POST",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    access_token = token_response.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="카카오 액세스 토큰을 발급받지 못했습니다.",
        )
    return access_token


# 카카오 사용자 정보 조회 함수
def _get_kakao_user(kakao_access_token: str) -> Dict[str, Any]:
    return _request_json(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {kakao_access_token}"},
    )


# 전화번호 형식 정리 함수
def _normalize_phone_number(phone_number: Optional[str]) -> Optional[str]:
    if not phone_number:
        return None
    return phone_number.replace(" ", "").replace("-", "")


# 카카오 사용자 조회 또는 자동 가입 함수
def _get_or_create_kakao_user(db: Session, kakao_user: Dict[str, Any]) -> User:
    kakao_id = str(kakao_user["id"])
    kakao_account = kakao_user.get("kakao_account") or {}
    email = kakao_account.get("email")
    phone_number = _normalize_phone_number(kakao_account.get("phone_number"))

    # kakao_id 기준 기존 사용자 조회
    user = db.query(User).filter(User.kakao_id == kakao_id).first()

    # 이메일 기준 기존 계정 추가 조회
    if user is None and email:
        user = db.query(User).filter(User.email == email).first()

    if user is None:
        # 신규 카카오 사용자 자동 가입
        user = User(
            email=email,
            phone_number=phone_number,
            kakao_id=kakao_id,
            login_type="kakao",
        )
        db.add(user)
    else:
        # 기존 사용자 카카오 정보 보충
        user.kakao_id = kakao_id
        user.login_type = "kakao"
        if email and not user.email:
            user.email = email
        if phone_number and not user.phone_number:
            user.phone_number = phone_number

    db.commit()
    db.refresh(user)
    return user


# 일반 회원가입 중복값 확인 함수
def _find_duplicate_local_user(db: Session, payload: LocalSignupRequest) -> Optional[str]:
    phone_number = _normalize_phone_number(payload.phone_number)

    if db.query(User).filter(User.username == payload.username).first() is not None:
        return "이미 사용 중인 사용자명입니다."
    if payload.email and db.query(User).filter(User.email == payload.email).first() is not None:
        return "이미 사용 중인 이메일입니다."
    if db.query(User).filter(User.phone_number == phone_number).first() is not None:
        return "이미 사용 중인 전화번호입니다."
    return None


# 카카오 로그인 시작 엔드포인트
@app.get("/auth/kakao/login")
def kakao_login(redirect_uri: Optional[str] = Query(default=None)) -> RedirectResponse:
    uri = _get_redirect_uri(redirect_uri)
    query = urlencode(
        {
            "client_id": settings.KAKAO_REST_API_KEY,
            "redirect_uri": uri,
            "response_type": "code",
        }
    )
    return RedirectResponse(f"https://kauth.kakao.com/oauth/authorize?{query}")


# 일반 회원가입 엔드포인트
@app.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def local_signup(payload: LocalSignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    duplicate_message = _find_duplicate_local_user(db, payload)
    if duplicate_message:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=duplicate_message,
        )

    # 일반 사용자 생성
    user = User(
        username=payload.username,
        password=hash_password(payload.password),
        email=payload.email,
        phone_number=_normalize_phone_number(payload.phone_number),
        latitude=payload.latitude,
        longitude=payload.longitude,
        login_type="local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 회원가입 성공 후 JWT 발급
    return TokenResponse(
        access_token=create_access_token(user.id),
        needs_onboarding=False,
        user=user,
    )


# 일반 로그인 엔드포인트
@app.post("/auth/login", response_model=TokenResponse)
def local_login(payload: LocalLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or user.login_type != "local" or not user.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자명 또는 비밀번호가 올바르지 않습니다.",
        )

    # 비밀번호 해시 검증
    if not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자명 또는 비밀번호가 올바르지 않습니다.",
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        needs_onboarding=False,
        user=user,
    )


# 카카오 로그인 콜백 엔드포인트
@app.get("/auth/kakao/callback", response_model=TokenResponse)
def kakao_callback(
    code: str,
    redirect_uri: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    uri = _get_redirect_uri(redirect_uri)
    kakao_access_token = _exchange_kakao_token(code, uri)
    kakao_user = _get_kakao_user(kakao_access_token)
    user = _get_or_create_kakao_user(db, kakao_user)

    # 전화번호 없을 경우 온보딩 필요 표시
    return TokenResponse(
        access_token=create_access_token(user.id),
        needs_onboarding=user.phone_number is None,
        user=user,
    )


# 온보딩 정보 업데이트 엔드포인트
@app.patch("/auth/onboarding", response_model=UserResponse)
def complete_onboarding(
    payload: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if payload.phone_number is not None:
        # 온보딩 전화번호 중복 확인
        phone_number = _normalize_phone_number(payload.phone_number)
        duplicate_user = (
            db.query(User)
            .filter(and_(User.phone_number == phone_number, User.id != current_user.id))
            .first()
        )
        if duplicate_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 사용 중인 전화번호입니다.",
            )
        current_user.phone_number = phone_number

    # 선택 입력된 위치 정보 업데이트
    if payload.latitude is not None:
        current_user.latitude = payload.latitude
    if payload.longitude is not None:
        current_user.longitude = payload.longitude

    db.commit()
    db.refresh(current_user)
    return current_user


# 현재 로그인 사용자 조회 엔드포인트
@app.get("/users/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
