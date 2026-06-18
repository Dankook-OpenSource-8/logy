ALTER TABLE users
ADD COLUMN IF NOT EXISTS last_attendance_date DATE;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS major VARCHAR;

CREATE TABLE IF NOT EXISTS user_pets (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL DEFAULT 'Logy',
    level INTEGER NOT NULL DEFAULT 1,
    total_exp INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE user_pets
ADD COLUMN IF NOT EXISTS pet_type VARCHAR NOT NULL DEFAULT 'cat';

ALTER TABLE user_pets
ADD COLUMN IF NOT EXISTS placed BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE user_pets
ADD COLUMN IF NOT EXISTS position_x INTEGER NOT NULL DEFAULT 0;

ALTER TABLE user_pets
ADD COLUMN IF NOT EXISTS position_y INTEGER NOT NULL DEFAULT 0;

UPDATE user_pets
SET pet_type = 'cat'
WHERE pet_type IS NULL OR pet_type NOT IN ('cat', 'dog');

UPDATE user_pets
SET level = 5
WHERE level > 5;

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

WITH duplicate_placements AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, furniture_item_id
            ORDER BY updated_at DESC, id DESC
        ) AS placement_rank
    FROM furniture_placements
)
DELETE FROM furniture_placements
USING duplicate_placements
WHERE furniture_placements.id = duplicate_placements.id
  AND duplicate_placements.placement_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_furniture_placements_user_item
ON furniture_placements (user_id, furniture_item_id);

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

INSERT INTO furniture_items (code, name, total_piece_count)
VALUES
    ('sofa', '소파', 5),
    ('chair', '의자', 5),
    ('tv', '티비', 5),
    ('lamp', '스탠드조명', 5),
    ('fridge', '냉장고', 5),
    ('bed', '침대', 5)
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    total_piece_count = EXCLUDED.total_piece_count;

INSERT INTO furniture_pieces (furniture_item_id, code, name, sort_order)
SELECT furniture_items.id, piece.code, furniture_items.name || ' 조각 ' || piece.sort_order, piece.sort_order
FROM furniture_items
CROSS JOIN (
    VALUES
        ('piece_1', 1),
        ('piece_2', 2),
        ('piece_3', 3),
        ('piece_4', 4),
        ('piece_5', 5)
) AS piece(code, sort_order)
WHERE furniture_items.code IN ('sofa', 'chair', 'tv', 'lamp', 'fridge', 'bed')
ON CONFLICT (furniture_item_id, code) DO NOTHING;
