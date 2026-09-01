"""Create MySQL ebay_store on TrueNAS and apply db/app_schema.sql.

Usage:
    python scripts/init_mysql.py
    python scripts/init_mysql.py --ping
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from credentials import (  # noqa: E402
    db_host,
    db_name,
    db_password,
    db_port,
    db_summary,
    db_user,
    sibling_root_password,
)

SCHEMA_PATH = ROOT / "db" / "app_schema.sql"


def connect(*, database: str | None = None, user: str | None = None, password: str | None = None):
    kwargs = {
        "host": db_host(),
        "port": db_port(),
        "user": user or db_user(),
        "password": password if password is not None else db_password(),
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def split_sql(sql: str) -> list[str]:
    statements = []
    for raw in sql.split(";"):
        statement = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("--")
        ).strip()
        if statement:
            statements.append(statement)
    return statements


def ensure_database() -> None:
    password = db_password()
    if not password:
        raise SystemExit(
            "No MySQL password found. Copy .env.example to .env or reuse Resume-Builder credentials."
        )
    conn = connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name()}` "
                "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()
            cur.close()
            return
        except mysql.connector.Error:
            cur.execute("SHOW DATABASES")
            names = {row[0] for row in cur.fetchall()}
            cur.close()
            if db_name() in names:
                return
    finally:
        conn.close()
    ensure_database_as_root()


def ensure_database_as_root() -> None:
    root_password = sibling_root_password()
    if not root_password:
        raise SystemExit(
            f"User {db_user()} cannot create `{db_name()}` and no Resume-Builder root password was found."
        )
    conn = connect(user="root", password=root_password)
    try:
        cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name()}` "
            "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
        )
        cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name()}`.* TO '{db_user()}'@'%'")
        cur.execute("FLUSH PRIVILEGES")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def apply_schema() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(database=db_name())
    try:
        cur = conn.cursor()
        for statement in split_sql(sql):
            cur.execute(statement)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def ping() -> dict[str, str]:
    conn = connect(database=db_name())
    try:
        cur = conn.cursor()
        cur.execute("SELECT DATABASE(), VERSION()")
        database, version = cur.fetchone()
        cur.execute("SHOW TABLES")
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        return {
            "database": database or "(none)",
            "version": str(version),
            "user": db_user(),
            "host": db_host(),
            "tables": ", ".join(tables) if tables else "(none)",
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize MySQL ebay_store on TrueNAS.")
    parser.add_argument("--ping", action="store_true", help="Connect and list tables; do not create.")
    args = parser.parse_args()

    summary = db_summary()
    print(
        f"MySQL {summary['user']}@{summary['host']}:{summary['port']}/{summary['name']} "
        f"(password: {summary['password_source']})"
    )
    if args.ping:
        info = ping()
        for key, value in info.items():
            print(f"  {key}: {value}")
        return
    ensure_database()
    apply_schema()
    info = ping()
    print("Database ready.")
    for key, value in info.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
