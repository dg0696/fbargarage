"""SQLite connection helpers for the eBay store database."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "db" / "ebay_store.db"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def get_db_path(db_path=None):
    return Path(db_path) if db_path else DEFAULT_DB_PATH


def connect(db_path=None):
    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(db_path=None):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path=None):
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with db_session(db_path) as conn:
        conn.executescript(schema_sql)
