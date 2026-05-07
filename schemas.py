from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# 사용자 응답 스키마
class UserResponse(BaseModel):
    id: int
    username: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_away_mode: bool
    away_end_date: Optional[date] = None
    kakao_id: Optional[str] = None
    login_type: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    # SQLAlchemy 모델 객체 변환 허용
    model_config = {"from_attributes": True}


# 토큰 응답 스키마
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    needs_onboarding: bool
    user: UserResponse


# 일반 회원가입 요청 스키마
class LocalSignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    phone_number: str = Field(min_length=9, max_length=20)
    email: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# 일반 로그인 요청 스키마
class LocalLoginRequest(BaseModel):
    username: str
    password: str


# 온보딩 요청 스키마
class OnboardingRequest(BaseModel):
    phone_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
