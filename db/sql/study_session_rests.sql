-- Supabase SQL editor에서 기존 DB에 적용하는 타이머 휴식 로그 스키마입니다.
-- 하루 2회, 총 15분 제한은 API에서 서버 시각 기준으로 검증합니다.

CREATE TABLE IF NOT EXISTS study_session_rests (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    study_session_id INTEGER NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_study_session_rests_user_id
    ON study_session_rests(user_id);

CREATE INDEX IF NOT EXISTS ix_study_session_rests_study_session_id
    ON study_session_rests(study_session_id);

CREATE INDEX IF NOT EXISTS ix_study_session_rests_started_at
    ON study_session_rests(started_at);
