import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User

# Authorization: Bearer 토큰을 읽기 위한 설정
security = HTTPBearer()

# 비밀번호 해시 반복 횟수
PASSWORD_HASH_ITERATIONS = 100_000


# JWT용 base64 인코딩 함수
def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


# JWT용 base64 디코딩 함수
def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# 비밀번호 해시 생성 함수
def hash_password(password: str) -> str:
    # 비밀번호 해시용 salt 랜덤 생성
    salt = secrets.token_hex(16)

    # PBKDF2 방식으로 비밀번호 해시 처리
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${password_hash}"


# 비밀번호 검증 함수
def verify_password(password: str, hashed_password: str) -> bool:
    try:
        # 저장된 해시 문자열 분리
        algorithm, iterations, salt, stored_hash = hashed_password.split("$")
        if algorithm != "pbkdf2_sha256":
            return False

        # 입력 비밀번호를 같은 방식으로 해시 후 비교
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(password_hash, stored_hash)
    except Exception:
        return False


# JWT access token 발급 함수
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)

    # JWT payload 설정
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}

    if settings.JWT_ALGORITHM != "HS256":
        raise ValueError("Only HS256 JWT signing is supported.")

    # JWT 서명 대상 문자열 생성
    signing_input = ".".join(
        [
            _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )

    # 서버 비밀키로 JWT 서명
    signature = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


# JWT access token 검증 함수
def verify_access_token(token: str) -> int:
    # 인증 실패 공통 에러
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않은 인증 토큰입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # JWT 세 부분 분리
        header_part, payload_part, signature_part = token.split(".")
        signing_input = f"{header_part}.{payload_part}"

        # 서버에서 다시 계산한 서명과 비교
        expected_signature = hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        received_signature = _base64url_decode(signature_part)

        if not hmac.compare_digest(expected_signature, received_signature):
            raise credentials_error

        # 토큰 만료 시간 확인
        payload = json.loads(_base64url_decode(payload_part))
        if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증 토큰이 만료되었습니다.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return int(payload["sub"])
    except HTTPException:
        raise
    except Exception as exc:
        raise credentials_error from exc


# 현재 로그인 사용자 조회 함수
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    # 보호 API용 현재 사용자 조회
    user_id = verify_access_token(credentials.credentials)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
