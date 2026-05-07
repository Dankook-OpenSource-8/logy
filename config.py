from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # .env 파일 변수명과 동일하게 작성
    # 카카오 REST API 키
    KAKAO_REST_API_KEY: str

    # 카카오 로그인 redirect URI
    KAKAO_REDIRECT_URI: Optional[str] = None

    # 카카오 Client Secret
    KAKAO_CLIENT_SECRET: Optional[str] = None

    # Supabase PostgreSQL 접속 주소
    DATABASE_URL: str

    # JWT 서명 비밀키
    JWT_SECRET_KEY: str

    # JWT 알고리즘
    JWT_ALGORITHM: str = "HS256"

    # JWT 만료 시간
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # .env 파일을 읽어오겠다는 설정
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# 다른 파일에서 settings 객체를 import해서 사용
settings = Settings()
