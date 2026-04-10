from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


class AuthService:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def has_any_admin(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM admin_users").fetchone()
        return bool(row and int(row["total"]) > 0)

    def list_admin_usernames(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT username FROM admin_users ORDER BY username COLLATE NOCASE"
            ).fetchall()
        return [str(row["username"]) for row in rows]

    def create_or_update_admin(self, username: str, password: str) -> None:
        user = (username or "").strip()
        pwd = (password or "").strip()
        if not user or not pwd:
            raise ValueError("Informe login e senha validos.")

        password_hash = generate_password_hash(pwd)
        now = datetime.now().isoformat(timespec="seconds")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_users (username, password_hash, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash=excluded.password_hash,
                    updated_at=excluded.updated_at
                """,
                (user, password_hash, now),
            )
            conn.commit()

    def rename_admin(self, old_username: str, new_username: str) -> bool:
        old_user = (old_username or "").strip()
        new_user = (new_username or "").strip()
        if not old_user or not new_user:
            raise ValueError("Informe login atual e novo login.")

        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE admin_users SET username = ?, updated_at = ? WHERE username = ?",
                (new_user, datetime.now().isoformat(timespec="seconds"), old_user),
            )
            conn.commit()
        return cursor.rowcount > 0

    def update_password(self, username: str, new_password: str) -> bool:
        user = (username or "").strip()
        pwd = (new_password or "").strip()
        if not user or not pwd:
            raise ValueError("Informe login e nova senha.")

        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE admin_users SET password_hash = ?, updated_at = ? WHERE username = ?",
                (
                    generate_password_hash(pwd),
                    datetime.now().isoformat(timespec="seconds"),
                    user,
                ),
            )
            conn.commit()
        return cursor.rowcount > 0

    def delete_admin(self, username: str) -> bool:
        user = (username or "").strip()
        if not user:
            raise ValueError("Informe o login para exclusao.")

        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM admin_users WHERE username = ?", (user,))
            conn.commit()
        return cursor.rowcount > 0

    def authenticate(self, username: str, password: str) -> bool:
        user = (username or "").strip()
        pwd = (password or "").strip()
        if not user or not pwd:
            return False

        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM admin_users WHERE username = ?",
                (user,),
            ).fetchone()

        if not row:
            return False

        return check_password_hash(str(row["password_hash"]), pwd)
