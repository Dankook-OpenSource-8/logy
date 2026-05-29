ALTER TABLE users
ADD COLUMN IF NOT EXISTS last_attendance_date DATE;

CREATE TABLE IF NOT EXISTS user_pets (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL DEFAULT 'Logy',
    level INTEGER NOT NULL DEFAULT 1,
    total_exp INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS furniture_items (
    id SERIAL PRIMARY KEY,
    code VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL,
    total_piece_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS furniture_pieces (
    id SERIAL PRIMARY KEY,
    furniture_item_id INTEGER NOT NULL REFERENCES furniture_items(id) ON DELETE CASCADE,
    code VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_furniture_piece_item_code UNIQUE (furniture_item_id, code)
);

CREATE TABLE IF NOT EXISTS user_furniture_piece_progress (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    furniture_piece_id INTEGER NOT NULL REFERENCES furniture_pieces(id) ON DELETE CASCADE,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_furniture_piece_progress UNIQUE (user_id, furniture_piece_id)
);

CREATE TABLE IF NOT EXISTS furniture_placements (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    furniture_item_id INTEGER NOT NULL REFERENCES furniture_items(id) ON DELETE CASCADE,
    placed BOOLEAN NOT NULL DEFAULT FALSE,
    position_x INTEGER NOT NULL DEFAULT 0,
    position_y INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reward_ledgers (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    study_session_id INTEGER NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    auth_log_id INTEGER NOT NULL UNIQUE REFERENCES auth_logs(id) ON DELETE CASCADE,
    verified_seconds INTEGER NOT NULL DEFAULT 0,
    pet_exp INTEGER NOT NULL DEFAULT 0,
    attendance_bonus_exp INTEGER NOT NULL DEFAULT 0,
    furniture_piece_id INTEGER REFERENCES furniture_pieces(id) ON DELETE SET NULL,
    furniture_progress_percent INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO furniture_items (code, name, total_piece_count)
VALUES ('desk', '책상', 5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO furniture_pieces (furniture_item_id, code, name, sort_order)
SELECT furniture_items.id, piece.code, piece.name, piece.sort_order
FROM furniture_items
CROSS JOIN (
    VALUES
        ('leg_1', '책상 다리 1', 1),
        ('leg_2', '책상 다리 2', 2),
        ('leg_3', '책상 다리 3', 3),
        ('leg_4', '책상 다리 4', 4),
        ('top', '책상 상판', 5)
) AS piece(code, name, sort_order)
WHERE furniture_items.code = 'desk'
ON CONFLICT (furniture_item_id, code) DO NOTHING;
