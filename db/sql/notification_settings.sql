CREATE TABLE IF NOT EXISTS user_notification_settings (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    all_notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    random_auth_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    group_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    reward_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    quiet_start_time TIME,
    quiet_end_time TIME,
    quiet_weekdays VARCHAR NOT NULL DEFAULT '0,1,2,3,4',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_notification_settings_user UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS ix_user_notification_settings_user_id
    ON user_notification_settings(user_id);
