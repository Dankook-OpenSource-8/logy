from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, Boolean
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

    # 가입 시각과 마지막 정보 갱신 시각
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sessions = relationship("StudySession", back_populates="owner", cascade="all, delete-orphan")
    auth_logs = relationship("AuthLog", back_populates="owner", cascade="all, delete-orphan")
    focus_interruptions = relationship("FocusInterruption", back_populates="owner", cascade="all, delete-orphan")
    push_tokens = relationship("UserPushToken", back_populates="owner", cascade="all, delete-orphan")
    
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

# 6. 인증 로그 테이블 (이미지의 study_session_id 연결 반영)
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
    # 인증 결과 상태 (성공, 실패, 시간초과)
    status = Column(Enum("성공", "실패", "시간초과", name="auth_status"), nullable=False)
    # 인증 처리 중 발생한 오류 메시지
    error_message = Column(String, nullable=True)
    # 같은 세션에서 인증 시도 횟수
    auth_attempt_count = Column(Integer, default=1)

    # 인증 로그 생성 시각
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="auth_logs")
    session = relationship("StudySession", back_populates="auth_logs")
