-- Supabase SQL editor에서 기존 DB에 적용하는 그룹/소셜 기능 스키마입니다.
-- 새 DB에서는 SQLAlchemy 모델과 create_tables.py로도 생성됩니다.

CREATE TABLE IF NOT EXISTS study_groups (
    id SERIAL PRIMARY KEY,
    owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    invite_code VARCHAR NOT NULL UNIQUE,
    visibility VARCHAR NOT NULL DEFAULT 'private',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE study_groups
    ADD COLUMN IF NOT EXISTS visibility VARCHAR NOT NULL DEFAULT 'private';

CREATE INDEX IF NOT EXISTS ix_study_groups_owner_user_id
    ON study_groups(owner_user_id);

CREATE INDEX IF NOT EXISTS ix_study_groups_invite_code
    ON study_groups(invite_code);

CREATE INDEX IF NOT EXISTS ix_study_groups_visibility
    ON study_groups(visibility);

CREATE TABLE IF NOT EXISTS group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR NOT NULL DEFAULT 'member',
    online_status VARCHAR NOT NULL DEFAULT 'offline',
    study_status VARCHAR NOT NULL DEFAULT 'idle',
    active_study_session_id INTEGER REFERENCES study_sessions(id) ON DELETE SET NULL,
    last_seen_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_group_members_group_user UNIQUE (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_group_members_group_id
    ON group_members(group_id);

CREATE INDEX IF NOT EXISTS ix_group_members_user_id
    ON group_members(user_id);

ALTER TABLE group_members
    ADD COLUMN IF NOT EXISTS farm_pet_position_x INTEGER NOT NULL DEFAULT 0;

ALTER TABLE group_members
    ADD COLUMN IF NOT EXISTS farm_pet_position_y INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS group_poke_logs (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    sender_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message VARCHAR,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_group_poke_logs_group_id
    ON group_poke_logs(group_id);

CREATE INDEX IF NOT EXISTS ix_group_poke_logs_target_user_id
    ON group_poke_logs(target_user_id);

CREATE INDEX IF NOT EXISTS ix_group_poke_logs_created_at
    ON group_poke_logs(created_at);
