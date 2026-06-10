from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, Boolean, UniqueConstraint, Date, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
import enum
import uuid
from sqlalchemy.dialects.postgresql import UUID

# 1. 공부 세션 상태 (이미지의 active, completed, cancelled 반영)
class SessionStatus(enum.Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"

# 2. 사용자 정보 테이블 (이미지의 created_at, updated_at 반영)
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    real_name = Column(String, nullable=False)
    nickname = Column(String, unique=True, index=True, nullable=False)

    password = Column(String, nullable=False)  # 비밀번호

    # 사용자가 누적한 전체 공부 시간(초 단위)
    total_study_time = Column(Integer, default=0)
    # 사용자의 연속 출석 일수 또는 인증 성공 연속일
    streak_days = Column(Integer, default=0)
    # 하루 첫 인증 성공을 출석으로 인정할 때 마지막으로 처리한 날짜
    last_attendance_date = Column(Date, nullable=True)

    # 가입 시각과 마지막 정보 갱신 시각
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sessions = relationship("StudySession", back_populates="owner", cascade="all, delete-orphan")
    auth_logs = relationship("AuthLog", back_populates="owner", cascade="all, delete-orphan")
    focus_interruptions = relationship("FocusInterruption", back_populates="owner", cascade="all, delete-orphan")
    push_tokens = relationship("UserPushToken", back_populates="owner", cascade="all, delete-orphan")
    notification_setting = relationship("UserNotificationSetting", back_populates="owner", uselist=False, cascade="all, delete-orphan")
    rest_logs = relationship("StudySessionRest", back_populates="owner", cascade="all, delete-orphan")
    group_memberships = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    owned_groups = relationship("StudyGroup", back_populates="owner", cascade="all, delete-orphan")
    pet = relationship("UserPet", back_populates="owner", uselist=False, cascade="all, delete-orphan")
    furniture_progress = relationship("UserFurniturePieceProgress", back_populates="owner", cascade="all, delete-orphan")
    furniture_placements = relationship("FurniturePlacement", back_populates="owner", cascade="all, delete-orphan")
    reward_logs = relationship("RewardLedger", back_populates="owner", cascade="all, delete-orphan")
    
# 3. 공부 세션 테이블 (이미지의 end_time, status, next_auth_time 반영)
class StudySession(Base):
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    # 사용자가 이 세션에서 선택한 과목 이름 또는 세션 제목
    subject = Column(String, nullable=True)
    # 이 세션에서 달성하려는 목표나 메모
    goal_note = Column(Text, nullable=True)

    # 세션 시작 시각
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    # 세션 종료 시각 (세션 종료 시 기록)
    end_time = Column(DateTime(timezone=True), nullable=True)
    # 이 세션에서 실제로 공부한 총 초
    total_seconds = Column(Integer, default=0)

    # 세션 상태: active, completed, cancelled
    status = Column(Enum(SessionStatus), default=SessionStatus.active)
    # 인증 주기를 분 단위로 저장 (예: 60분)
    period_minutes = Column(Integer, default=60)
    # 다음 인증 목표 시각
    next_auth_time = Column(DateTime(timezone=True))

    # 일시정지 여부와 마지막 일시정지 시각
    is_paused = Column(Boolean, default=False)
    last_paused_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="sessions")
    auth_logs = relationship("AuthLog", back_populates="session", cascade="all, delete-orphan")
    focus_interruptions = relationship("FocusInterruption", back_populates="session", cascade="all, delete-orphan")
    rest_logs = relationship("StudySessionRest", back_populates="session", cascade="all, delete-orphan")
    active_group_members = relationship("GroupMember", back_populates="active_session")


# 4. 앱 포커스 이탈 로그 테이블
class FocusInterruption(Base):
    __tablename__ = "focus_interruptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    study_session_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False)

    # 앱에서 감지한 이벤트 종류: app_background, app_inactive, grace_timeout 등
    event_type = Column(String, nullable=False)
    # 클라이언트가 참고용으로 보낸 감지 시각입니다. 판정 기준은 서버 시각을 사용합니다.
    client_event_at = Column(DateTime(timezone=True), nullable=True)
    # 서버가 이탈 로그를 수신한 시각입니다.
    interrupted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # 프론트가 적용한 복귀 유예 시간(초)
    grace_seconds = Column(Integer, default=3, nullable=False)
    # 3초 내 복귀 실패 등으로 패널티가 확정되었는지 여부
    penalty_applied = Column(Boolean, default=False, nullable=False)

    owner = relationship("User", back_populates="focus_interruptions")
    session = relationship("StudySession", back_populates="focus_interruptions")


# 5. 타이머 휴식 로그 테이블
class StudySessionRest(Base):
    __tablename__ = "study_session_rests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    study_session_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="rest_logs")
    session = relationship("StudySession", back_populates="rest_logs")


# 5. Expo 앱 푸시 알림 토큰 테이블
class UserPushToken(Base):
    __tablename__ = "user_push_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    expo_push_token = Column(String, unique=True, index=True, nullable=False)
    platform = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="push_tokens")


class UserNotificationSetting(Base):
    __tablename__ = "user_notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    all_notifications_enabled = Column(Boolean, default=True, nullable=False)
    random_auth_enabled = Column(Boolean, default=True, nullable=False)
    group_enabled = Column(Boolean, default=True, nullable=False)
    reward_enabled = Column(Boolean, default=True, nullable=False)
    quiet_hours_enabled = Column(Boolean, default=False, nullable=False)
    quiet_start_time = Column(Time, nullable=True)
    quiet_end_time = Column(Time, nullable=True)
    quiet_weekdays = Column(String, default="0,1,2,3,4", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="notification_setting")


# 6. 친구들과 함께 공부하는 그룹
class StudyGroup(Base):
    __tablename__ = "study_groups"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String, nullable=False)
    invite_code = Column(String, unique=True, index=True, nullable=False)
    visibility = Column(String, default="private", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="owned_groups", foreign_keys=[owner_user_id])
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    poke_logs = relationship("GroupPokeLog", back_populates="group", cascade="all, delete-orphan")


# 7. 그룹 멤버와 마지막 활동 상태
class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("study_groups.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String, default="member", nullable=False)
    online_status = Column(String, default="offline", nullable=False)
    study_status = Column(String, default="idle", nullable=False)
    active_study_session_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="SET NULL"), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    group = relationship("StudyGroup", back_populates="members")
    user = relationship("User", back_populates="group_memberships")
    active_session = relationship("StudySession", back_populates="active_group_members")


# 8. 콕 찌르기 기록
class GroupPokeLog(Base):
    __tablename__ = "group_poke_logs"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("study_groups.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    message = Column(String, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("StudyGroup", back_populates="poke_logs")
    sender = relationship("User", foreign_keys=[sender_user_id])
    target = relationship("User", foreign_keys=[target_user_id])

# 9. 인증 로그 테이블 (이미지의 study_session_id 연결 반영)
class AuthLog(Base):
    __tablename__ = "auth_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # 어느 세션인지 명확히 연결!
    study_session_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False)

    # Supabase Storage에 업로드된 영상 URL
    video_url = Column(String, nullable=False)
    # 인증 영상의 썸네일 URL을 저장할 경우
    thumbnail_url = Column(String, nullable=True)
    # 인증 결과 상태 (대기, 성공, 실패, 시간초과)
    status = Column(Enum("대기", "성공", "실패", "시간초과", name="auth_status"), nullable=False)
    # 인증 처리 중 발생한 오류 메시지
    error_message = Column(String, nullable=True)
    # AI 검증 총점과 세부 사유
    verification_score = Column(Integer, nullable=True)
    verification_reason = Column(Text, nullable=True)
    scene_score = Column(Integer, nullable=True)
    text_score = Column(Integer, nullable=True)
    quality_score = Column(Integer, nullable=True)
    forbidden_penalty = Column(Integer, nullable=True)
    representative_frame_path = Column(String, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    # 같은 세션에서 인증 시도 횟수
    auth_attempt_count = Column(Integer, default=1)

    # 인증 로그 생성 시각
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="auth_logs")
    session = relationship("StudySession", back_populates="auth_logs")
    reward_log = relationship("RewardLedger", back_populates="auth_log", uselist=False)


# 10. 사용자 펫 성장 상태
class UserPet(Base):
    __tablename__ = "user_pets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    name = Column(String, default="Logy", nullable=False)
    level = Column(Integer, default=1, nullable=False)
    total_exp = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="pet")


# 11. 가구 종류
class FurnitureItem(Base):
    __tablename__ = "furniture_items"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    total_piece_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    pieces = relationship("FurniturePiece", back_populates="furniture_item", cascade="all, delete-orphan")
    placements = relationship("FurniturePlacement", back_populates="furniture_item")


# 12. 가구를 구성하는 개별 조각
class FurniturePiece(Base):
    __tablename__ = "furniture_pieces"
    __table_args__ = (
        UniqueConstraint("furniture_item_id", "code", name="uq_furniture_piece_item_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    furniture_item_id = Column(Integer, ForeignKey("furniture_items.id", ondelete="CASCADE"), index=True, nullable=False)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    furniture_item = relationship("FurnitureItem", back_populates="pieces")
    user_progress = relationship("UserFurniturePieceProgress", back_populates="furniture_piece", cascade="all, delete-orphan")


# 13. 사용자의 가구 조각 진행도
class UserFurniturePieceProgress(Base):
    __tablename__ = "user_furniture_piece_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "furniture_piece_id", name="uq_user_furniture_piece_progress"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    furniture_piece_id = Column(Integer, ForeignKey("furniture_pieces.id", ondelete="CASCADE"), index=True, nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    completed_count = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="furniture_progress")
    furniture_piece = relationship("FurniturePiece", back_populates="user_progress")


# 14. 완성 가구 배치 정보
class FurniturePlacement(Base):
    __tablename__ = "furniture_placements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    furniture_item_id = Column(Integer, ForeignKey("furniture_items.id", ondelete="CASCADE"), index=True, nullable=False)
    placed = Column(Boolean, default=False, nullable=False)
    position_x = Column(Integer, default=0, nullable=False)
    position_y = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User", back_populates="furniture_placements")
    furniture_item = relationship("FurnitureItem", back_populates="placements")


# 15. 인증 성공 보상 정산 기록
class RewardLedger(Base):
    __tablename__ = "reward_ledgers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    study_session_id = Column(Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    auth_log_id = Column(Integer, ForeignKey("auth_logs.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    verified_seconds = Column(Integer, default=0, nullable=False)
    pet_exp = Column(Integer, default=0, nullable=False)
    attendance_bonus_exp = Column(Integer, default=0, nullable=False)
    furniture_piece_id = Column(Integer, ForeignKey("furniture_pieces.id", ondelete="SET NULL"), nullable=True)
    furniture_progress_percent = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="reward_logs")
    auth_log = relationship("AuthLog", back_populates="reward_log")
    furniture_piece = relationship("FurniturePiece")
