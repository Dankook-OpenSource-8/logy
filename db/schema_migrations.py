from pathlib import Path

from sqlalchemy import text

from db.database import engine


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip(";").strip())
            current = []

    if current:
        statements.append("\n".join(current).strip())

    return statements


def ensure_group_social_schema() -> None:
    sql_path = Path(__file__).resolve().parent / "sql" / "group_social.sql"
    sql = sql_path.read_text(encoding="utf-8")

    with engine.begin() as connection:
        for statement in _split_sql_statements(sql):
            connection.execute(text(statement))
