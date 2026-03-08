import sqlite3
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _BASE_DIR / "schema.sql"


def init_db(db_path: str) -> None:
    """Create the database and apply schema.sql if it does not already exist."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    schema = _SCHEMA_PATH.read_text()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a database connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
