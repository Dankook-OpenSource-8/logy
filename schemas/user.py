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
    start_time: datetime
    next_auth_time: datetime


class StudySessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str | None
    goal_note: str | None
    start_time: datetime
    end_time: datetime | None
    total_seconds: int
    status: str
    period_minutes: int
    next_auth_time: datetime | None
    is_paused: bool
    last_paused_at: datetime | None


class ActiveStudySessionResponse(BaseModel):
    active_session: StudySessionResponse | None


class StudySessionCompleteRequest(BaseModel):
    total_seconds: int = Field(..., ge=0, le=86400)


class StudySessionCompleteResponse(BaseModel):
    message: str
    study_session: StudySessionResponse


class FocusInterruptionCreateRequest(BaseModel):
    event_type: str = Field(default="app_background", min_length=1, max_length=50)
    client_event_at: datetime | None = None
    grace_seconds: int = Field(default=3, ge=0, le=60)
    penalty_applied: bool = False


class FocusInterruptionResponse(BaseModel):
    message: str
    focus_interruption_id: int
    study_session_id: int
    interrupted_at: datetime
    penalty_applied: bool
    session_status: str


class VideoUploadResponse(BaseModel):
    message: str
    video_url: str


class PushTokenRegisterRequest(BaseModel):
    expo_push_token: str = Field(..., min_length=1, max_length=255)
    platform: str | None = Field(default=None, max_length=20)


class PushTokenRegisterResponse(BaseModel):
    message: str
    push_token_id: int
