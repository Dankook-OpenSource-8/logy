-- Supabase SQL editor에서 기존 DB에 적용하는 AI 영상 검증 스키마입니다.
-- 새 DB를 만들 때는 SQLAlchemy 모델과 create_tables.py로도 컬럼이 생성됩니다.

DO $$
BEGIN
    ALTER TYPE auth_status ADD VALUE IF NOT EXISTS '대기';
EXCEPTION
    WHEN undefined_object THEN
        NULL;
END $$;

ALTER TABLE auth_logs
    ADD COLUMN IF NOT EXISTS verification_score INTEGER,
    ADD COLUMN IF NOT EXISTS verification_reason TEXT,
    ADD COLUMN IF NOT EXISTS scene_score INTEGER,
    ADD COLUMN IF NOT EXISTS text_score INTEGER,
    ADD COLUMN IF NOT EXISTS quality_score INTEGER,
    ADD COLUMN IF NOT EXISTS forbidden_penalty INTEGER,
    ADD COLUMN IF NOT EXISTS representative_frame_path VARCHAR,
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_auth_logs_verified_at
    ON auth_logs(verified_at);
