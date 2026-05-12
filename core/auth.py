import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "260000"))


def _b64encode(value: bytes) -> str:
    # 토큰과 해시 구성요소를 URL-safe base64 문자열로 변환합니다.
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def _b64decode(value: str) -> bytes:
    # padding이 제거된 URL-safe base64 문자열을 다시 bytes로 복원합니다.
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: str) -> str:
    # 토큰 payload를 서버 secret으로 서명합니다.
    digest = hmac.new(
        SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def hash_password(password: str) -> str:
    # 가입 시 비밀번호 원문 대신 저장할 PBKDF2 해시 문자열을 만듭니다.
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}$"
        f"{_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    # 로그인 시 입력 비밀번호와 DB 해시값이 일치하는지 비교합니다.
    try:
        algorithm, iterations, encoded_salt, encoded_digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        salt = _b64decode(encoded_salt)
        expected_digest = _b64decode(encoded_digest)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual_digest, expected_digest)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> str:
    # 로그인 성공 후 사용할 간단한 서명 토큰을 생성합니다.
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = _b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = _sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def verify_access_token(token: str) -> str:
    # Authorization 헤더의 토큰을 검증하고 user_id를 추출합니다.
    try:
        encoded_payload, signature = token.split(".", 1)
        expected_signature = _sign(encoded_payload)
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("invalid signature")

        payload = json.loads(_b64decode(encoded_payload))
        expires_at = int(payload["exp"])
        if expires_at < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired token")

        return str(payload["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 토큰입니다",
        ) from None

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """
    보호 API에서 현재 로그인한 사용자를 DB에서 조회합니다.
    """
    # 2. HTTPBearer가 토큰 유무 & Bearer 형식을 다 검사해주므로 바로 토큰만 뽑아씁니다.
    token = credentials.credentials

    # 3. 기존 토큰 검증 로직
    user_id = verify_access_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다",
        )
        
    return user