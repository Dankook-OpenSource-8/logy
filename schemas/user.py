from datetime import date, datetime
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


class StudySessionStartResponse(BaseModel):
    message: str
    study_session_id: int
    start_time: datetime
    next_auth_time: datetime
    auth_expires_at: datetime


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
    auth_expires_at: datetime | None
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


class FocusRiskItem(BaseModel):
    # 히트맵의 한 칸에 들어갈 요일/시간대별 분석 결과입니다.
    dayOfWeek: int
    hour: int
    riskScore: float
    riskLevel: str
    failureRate: float
    baselineDiff: float
    totalAttempts: int
    failedAttempts: int
    reason: str


class CollapsePredictionResponse(BaseModel):
    # 경고 배너에서 바로 쓰는 집중 붕괴 예측 값입니다.
    riskStartMinute: int | None
    predictedCollapseMinute: int | None
    riskLevel: str
    message: str
    sampleSize: int


class FocusAnalyticsSummaryResponse(BaseModel):
    # 차트를 보지 않아도 핵심 패턴을 읽을 수 있는 요약 정보입니다.
    highestRiskDay: str | None
    highestRiskHour: int | None
    riskMultiplier: float
    recommendation: str


class FocusAnalyticsMetadataResponse(BaseModel):
    # 프론트에서 빈 상태, 신뢰도 문구, 디버깅에 활용할 보조 지표입니다.
    totalAttempts: int
    failedAttempts: int
    baselineFailureRate: float
    recentFailureRate: float
    isEnoughData: bool


class FocusAnalyticsResponse(BaseModel):
    riskMap: list[FocusRiskItem]
    collapsePrediction: CollapsePredictionResponse
    summary: FocusAnalyticsSummaryResponse
    metadata: FocusAnalyticsMetadataResponse


class StudyArchiveAuthLogResponse(BaseModel):
    authLogId: int
    status: str
    videoUrl: str
    thumbnailUrl: str | None
    verificationScore: int | None
    verificationReason: str | None
    createdAt: datetime
    verifiedAt: datetime | None


class StudyArchiveSessionResponse(BaseModel):
    studySessionId: int
    subject: str | None
    goalNote: str | None
    startTime: datetime
    endTime: datetime | None
    totalSeconds: int
    status: str
    authSuccessCount: int
    authFailedCount: int
    authPendingCount: int
    authTimeoutCount: int
    authLogs: list[StudyArchiveAuthLogResponse]


class StudyArchiveDayResponse(BaseModel):
    date: date
    totalSeconds: int
    sessionCount: int
    completedCount: int
    failedCount: int
    authSuccessCount: int
    authFailedCount: int
    authPendingCount: int
    authTimeoutCount: int
    sessions: list[StudyArchiveSessionResponse]


class StudyArchivePeriodResponse(BaseModel):
    period: str
    startDate: date
    endDate: date
    totalSeconds: int
    sessionCount: int
    completedCount: int
    failedCount: int
    authSuccessCount: int
    authFailedCount: int
    authPendingCount: int
    authTimeoutCount: int
    averageDailySeconds: int
    days: list[StudyArchiveDayResponse]


class VideoUploadResponse(BaseModel):
    message: str
    video_url: str


class VideoVerificationRequest(BaseModel):
    study_session_id: int = Field(..., ge=1)
    video_url: str = Field(..., min_length=1, max_length=2048)
    captured_at: datetime | None = None


class VideoVerificationResponse(BaseModel):
    message: str
    auth_log_id: int
    status: str
    auth_expires_at: datetime | None = None


class VideoVerificationResultResponse(BaseModel):
    auth_log_id: int
    study_session_id: int
    status: str
    video_url: str
    verification_score: int | None
    verification_reason: str | None
    scene_score: int | None
    text_score: int | None
    quality_score: int | None
    forbidden_penalty: int | None
    representative_frame_path: str | None
    created_at: datetime
    verified_at: datetime | None


class PushTokenRegisterRequest(BaseModel):
    expo_push_token: str = Field(..., min_length=1, max_length=255)
    platform: str | None = Field(default=None, max_length=20)


class PushTokenRegisterResponse(BaseModel):
    message: str
    push_token_id: int


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class GroupResponse(BaseModel):
    id: int
    name: str
    invite_code: str
    owner_user_id: UUID
    member_count: int
    group_total_study_seconds: int
    created_at: datetime


class GroupInviteResponse(BaseModel):
    group_id: int
    invite_code: str


class GroupJoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=32)


class GroupJoinResponse(BaseModel):
    message: str
    group: GroupResponse


class GroupMemberStatusUpdateRequest(BaseModel):
    online_status: str = Field(default="online", max_length=20)
    study_status: str = Field(default="idle", max_length=20)
    active_study_session_id: int | None = Field(default=None, ge=1)


class GroupMemberResponse(BaseModel):
    user_id: UUID
    nickname: str
    role: str
    online_status: str
    study_status: str
    active_study_session_id: int | None
    last_seen_at: datetime | None
    total_study_seconds: int


class GroupMembersResponse(BaseModel):
    group_id: int
    group_name: str
    group_total_study_seconds: int
    members: list[GroupMemberResponse]


class GroupPokeCreateRequest(BaseModel):
    target_user_id: UUID
    message: str | None = Field(default=None, max_length=100)


class GroupPokeResponse(BaseModel):
    message: str
    poke_id: int
    group_id: int
    sender_user_id: UUID
    target_user_id: UUID
    created_at: datetime
