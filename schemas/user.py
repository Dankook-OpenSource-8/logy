from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from core.timezone import to_kst


class KSTBaseModel(BaseModel):
    @field_serializer("*", when_used="json")
    def serialize_kst_datetimes(self, value):
        if isinstance(value, datetime):
            converted = to_kst(value)
            return converted.isoformat() if converted is not None else None
        return value


class UserSignupRequest(KSTBaseModel):
    real_name: str = Field(..., min_length=1, max_length=100)
    nickname: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)


class UserLoginRequest(KSTBaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(KSTBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    real_name: str
    nickname: str
    total_study_time: int
    streak_days: int
    created_at: datetime
    updated_at: datetime


class AuthResponse(KSTBaseModel):
    message: str
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class NicknameCheckResponse(KSTBaseModel):
    nickname: str
    available: bool


class StudySessionStartRequest(KSTBaseModel):
    subject: str | None = Field(default=None, max_length=100)
    goal_note: str | None = Field(default=None, max_length=500)


class StudySessionStartResponse(KSTBaseModel):
    message: str
    study_session_id: int
    start_time: datetime
    next_auth_time: datetime
    auth_expires_at: datetime


class StudySessionResponse(KSTBaseModel):
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


class ActiveStudySessionResponse(KSTBaseModel):
    active_session: StudySessionResponse | None


class StudySessionRestStatusResponse(KSTBaseModel):
    study_session_id: int
    is_paused: bool
    daily_rest_count: int
    daily_rest_seconds: int
    remaining_rest_count: int
    remaining_rest_seconds: int
    active_rest_id: int | None
    active_rest_started_at: datetime | None


class StudySessionRestStartResponse(StudySessionRestStatusResponse):
    message: str
    rest_id: int


class StudySessionRestEndResponse(StudySessionRestStatusResponse):
    message: str
    rest_id: int
    rest_seconds: int


class StudySessionCompleteRequest(KSTBaseModel):
    total_seconds: int = Field(..., ge=0, le=86400)


class StudySessionCompleteResponse(KSTBaseModel):
    message: str
    study_session: StudySessionResponse


class FocusInterruptionCreateRequest(KSTBaseModel):
    event_type: str = Field(default="app_background", min_length=1, max_length=50)
    client_event_at: datetime | None = None
    grace_seconds: int = Field(default=3, ge=0, le=60)
    penalty_applied: bool = False


class FocusInterruptionResponse(KSTBaseModel):
    message: str
    focus_interruption_id: int
    study_session_id: int
    interrupted_at: datetime
    penalty_applied: bool
    session_status: str


class FocusRiskItem(KSTBaseModel):
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


class CollapsePredictionResponse(KSTBaseModel):
    # 경고 배너에서 바로 쓰는 집중 붕괴 예측 값입니다.
    riskStartMinute: int | None
    predictedCollapseMinute: int | None
    riskLevel: str
    message: str
    sampleSize: int


class FocusAnalyticsSummaryResponse(KSTBaseModel):
    # 차트를 보지 않아도 핵심 패턴을 읽을 수 있는 요약 정보입니다.
    highestRiskDay: str | None
    highestRiskHour: int | None
    riskMultiplier: float
    recommendation: str


class FocusAnalyticsMetadataResponse(KSTBaseModel):
    # 프론트에서 빈 상태, 신뢰도 문구, 디버깅에 활용할 보조 지표입니다.
    totalAttempts: int
    failedAttempts: int
    baselineFailureRate: float
    recentFailureRate: float
    isEnoughData: bool
    timezone: str


class FocusAnalyticsResponse(KSTBaseModel):
    riskMap: list[FocusRiskItem]
    collapsePrediction: CollapsePredictionResponse
    summary: FocusAnalyticsSummaryResponse
    metadata: FocusAnalyticsMetadataResponse


class StudyArchiveAuthLogResponse(KSTBaseModel):
    authLogId: int
    status: str
    videoUrl: str
    thumbnailUrl: str | None
    verificationScore: int | None
    verificationReason: str | None
    createdAt: datetime
    verifiedAt: datetime | None


class StudyArchiveSessionResponse(KSTBaseModel):
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


class StudyArchiveDayResponse(KSTBaseModel):
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


class StudyArchivePeriodResponse(KSTBaseModel):
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


class PetStageResponse(KSTBaseModel):
    level: int
    name: str
    requiredExp: int


class UserPetResponse(KSTBaseModel):
    petId: int
    name: str
    level: int
    stageName: str
    totalExp: int
    nextLevel: PetStageResponse | None
    expToNextLevel: int
    stages: list[PetStageResponse]


class FurniturePieceProgressResponse(KSTBaseModel):
    furniturePieceId: int
    code: str
    name: str
    progressPercent: int
    completedCount: int


class FurnitureItemProgressResponse(KSTBaseModel):
    furnitureItemId: int
    code: str
    name: str
    totalPieceCount: int
    completedPieceCount: int
    isCompleted: bool
    pieces: list[FurniturePieceProgressResponse]


class FurniturePlacementRequest(KSTBaseModel):
    furniture_item_id: int = Field(..., ge=1)
    placed: bool = True
    position_x: int = Field(default=0, ge=0, le=100)
    position_y: int = Field(default=0, ge=0, le=100)


class FurniturePlacementResponse(KSTBaseModel):
    placementId: int
    furnitureItemId: int
    furnitureCode: str
    furnitureName: str
    placed: bool
    positionX: int
    positionY: int


class RewardStateResponse(KSTBaseModel):
    pet: UserPetResponse
    furniture: list[FurnitureItemProgressResponse]
    placements: list[FurniturePlacementResponse]


class RewardSettlementResponse(KSTBaseModel):
    message: str
    rewardLogId: int
    verifiedSeconds: int
    petExp: int
    attendanceBonusExp: int
    streakDays: int
    furnitureProgressPercent: int
    furniturePieceId: int | None
    pet: UserPetResponse
    furniture: list[FurnitureItemProgressResponse]


class VideoUploadResponse(KSTBaseModel):
    message: str
    video_url: str
    auth_expires_at: datetime | None = None


class VideoVerificationRequest(KSTBaseModel):
    study_session_id: int = Field(..., ge=1)
    video_url: str = Field(..., min_length=1, max_length=2048)
    captured_at: datetime | None = None


class VideoVerificationResponse(KSTBaseModel):
    message: str
    auth_log_id: int
    status: str
    auth_expires_at: datetime | None = None


class VideoVerificationResultResponse(KSTBaseModel):
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
    auth_expires_at: datetime | None = None


class PushTokenRegisterRequest(KSTBaseModel):
    expo_push_token: str = Field(..., min_length=1, max_length=255)
    platform: str | None = Field(default=None, max_length=20)


class PushTokenRegisterResponse(KSTBaseModel):
    message: str
    push_token_id: int


class GroupCreateRequest(KSTBaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    visibility: str = Field(default="private", pattern="^(public|private)$")


class GroupResponse(KSTBaseModel):
    id: int
    name: str
    visibility: str
    invite_code: str
    owner_user_id: UUID
    member_count: int
    group_total_study_seconds: int
    group_today_study_seconds: int
    created_at: datetime


class GroupInviteResponse(KSTBaseModel):
    group_id: int
    invite_code: str


class GroupJoinRequest(KSTBaseModel):
    invite_code: str = Field(..., min_length=4, max_length=32)


class GroupJoinResponse(KSTBaseModel):
    message: str
    group: GroupResponse


class GroupMemberStatusUpdateRequest(KSTBaseModel):
    online_status: str = Field(default="online", max_length=20)
    study_status: str = Field(default="idle", max_length=20)
    active_study_session_id: int | None = Field(default=None, ge=1)


class GroupMemberResponse(KSTBaseModel):
    user_id: UUID
    nickname: str
    role: str
    online_status: str
    study_status: str
    active_study_session_id: int | None
    last_seen_at: datetime | None
    total_study_seconds: int


class GroupMembersResponse(KSTBaseModel):
    group_id: int
    group_name: str
    group_total_study_seconds: int
    group_today_study_seconds: int
    members: list[GroupMemberResponse]


class GroupPokeCreateRequest(KSTBaseModel):
    target_user_id: UUID
    message: str | None = Field(default=None, max_length=100)


class GroupPokeResponse(KSTBaseModel):
    message: str
    poke_id: int
    group_id: int
    sender_user_id: UUID
    target_user_id: UUID
    created_at: datetime
