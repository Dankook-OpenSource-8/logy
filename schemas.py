from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserSignupRequest(BaseModel):
    real_name: str = Field(..., min_length=1, max_length=100)
    nickname: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)


class UserLoginRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    real_name: str
    nickname: str
    total_study_time: int
    streak_days: int
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class NicknameCheckResponse(BaseModel):
    nickname: str
    available: bool
