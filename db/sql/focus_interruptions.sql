-- Supabase SQL editor에서 기존 DB에 적용하는 앱 이탈/푸시 알림 스키마입니다.
-- 새 DB를 만들 때는 SQLAlchemy 모델과 create_tables.py로도 테이블이 생성됩니다.

DO $$
BEGIN
    ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'failed';
EXCEPTION
    WHEN undefined_object THEN
        NULL;
END $$;

CREATE TABLE IF NOT EXISTS focus_interruptions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    study_session_id INTEGER NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    event_type VARCHAR NOT NULL,
    client_event_at TIMESTAMPTZ,
    interrupted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    grace_seconds INTEGER NOT NULL DEFAULT 3,
    penalty_applied BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_focus_interruptions_user_id
    ON focus_interruptions(user_id);

CREATE INDEX IF NOT EXISTS ix_focus_interruptions_study_session_id
    ON focus_interruptions(study_session_id);

CREATE INDEX IF NOT EXISTS ix_focus_interruptions_interrupted_at
    ON focus_interruptions(interrupted_at);

CREATE TABLE IF NOT EXISTS user_push_tokens (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expo_push_token VARCHAR NOT NULL UNIQUE,
    platform VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_user_push_tokens_user_id
    ON user_push_tokens(user_id);

CREATE INDEX IF NOT EXISTS ix_user_push_tokens_expo_push_token
    ON user_push_tokens(expo_push_token);
