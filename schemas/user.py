from datetime import datetime
from uuid import UUID
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

    id: UUID
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


class StudySessionStartRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=100)
    goal_note: str | None = Field(default=None, max_length=500)
    period_minutes: int = Field(default=60, ge=1, le=240)


class StudySessionStartResponse(BaseModel):
    message: str
    study_session_id: int
    next_auth_time: datetime


class VideoUploadResponse(BaseModel):
    message: str
    video_url: str
