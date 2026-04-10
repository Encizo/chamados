from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from app.models.ticket import Ticket


class DatabaseService:
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
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_row_number INTEGER UNIQUE NOT NULL,
                    data_hora TEXT,
                    local TEXT,
                    problema TEXT,
                    solicitante TEXT,
                    status TEXT,
                    resolution_reason TEXT DEFAULT '',
                    status_lock_until INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resolution_reasons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    note TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )

            columns = conn.execute("PRAGMA table_info(resolution_reasons)").fetchall()
            column_names = {row[1] for row in columns}
            if "note" not in column_names:
                conn.execute("ALTER TABLE resolution_reasons ADD COLUMN note TEXT DEFAULT ''")

            ticket_columns = conn.execute("PRAGMA table_info(tickets)").fetchall()
            ticket_column_names = {row[1] for row in ticket_columns}
            if "status_lock_until" not in ticket_column_names:
                conn.execute("ALTER TABLE tickets ADD COLUMN status_lock_until INTEGER DEFAULT 0")
            conn.commit()

    def upsert_tickets_from_sheet(self, tickets: list[Ticket]) -> None:
        with self._connect() as conn:
            incoming_row_numbers = {int(ticket.row_number) for ticket in tickets}

            for ticket in tickets:
                normalized_requester = self._normalize_requester_name(ticket.solicitante)
                conn.execute(
                    """
                    INSERT INTO tickets (
                        sheet_row_number, data_hora, local, problema, solicitante, status, resolution_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sheet_row_number) DO UPDATE SET
                        data_hora=excluded.data_hora,
                        local=excluded.local,
                        problema=excluded.problema,
                        solicitante=excluded.solicitante,
                        status=CASE
                            WHEN tickets.status_lock_until > CAST(strftime('%s','now') AS INTEGER)
                                 AND excluded.status <> tickets.status
                            THEN tickets.status
                            ELSE excluded.status
                        END,
                        resolution_reason=CASE
                            WHEN tickets.data_hora = excluded.data_hora
                             AND tickets.local = excluded.local
                             AND tickets.problema = excluded.problema
                             AND tickets.solicitante = excluded.solicitante
                            THEN tickets.resolution_reason
                            ELSE ''
                        END,
                        status_lock_until=CASE
                            WHEN tickets.status_lock_until > CAST(strftime('%s','now') AS INTEGER)
                                 AND excluded.status <> tickets.status
                            THEN tickets.status_lock_until
                            ELSE 0
                        END
                    """,
                    (
                        ticket.row_number,
                        ticket.data_hora,
                        ticket.local,
                        ticket.problema,
                        normalized_requester,
                        ticket.status,
                        "",
                    ),
                )

            if incoming_row_numbers:
                placeholders = ",".join("?" for _ in incoming_row_numbers)
                conn.execute(
                    f"DELETE FROM tickets WHERE sheet_row_number NOT IN ({placeholders})",
                    tuple(sorted(incoming_row_numbers)),
                )
            else:
                conn.execute("DELETE FROM tickets")

            conn.commit()

    def replace_tickets_from_sheet(self, tickets: list[Ticket]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM tickets")
            conn.commit()
        self.upsert_tickets_from_sheet(tickets)

    @staticmethod
    def _normalize_requester_name(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""

        words = [word for word in text.split() if word]
        return " ".join(word[:1].upper() + word[1:].lower() for word in words)

    def list_tickets(self) -> list[Ticket]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sheet_row_number, data_hora, local, problema, solicitante, status, resolution_reason
                FROM tickets
                ORDER BY sheet_row_number DESC
                """
            ).fetchall()

        return [
            Ticket(
                row_number=row["sheet_row_number"],
                data_hora=row["data_hora"] or "",
                local=row["local"] or "",
                problema=row["problema"] or "",
                solicitante=row["solicitante"] or "",
                status=self._canonical_status(row["status"] or "Em aberto"),
                resolution_reason=row["resolution_reason"] or "",
            )
            for row in rows
        ]

    def set_ticket_status(self, row_number: int, status: str, resolution_reason: str) -> None:
        canonical_status = self._canonical_status(status)
        lock_until = int(time.time()) + 120
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tickets
                SET status = ?, resolution_reason = ?, status_lock_until = ?
                WHERE sheet_row_number = ?
                """,
                (canonical_status, resolution_reason, lock_until, row_number),
            )
            conn.commit()

    def normalize_all_requester_names(self) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT sheet_row_number, solicitante FROM tickets"
            ).fetchall()

            for row in rows:
                normalized = self._normalize_requester_name(row["solicitante"] or "")
                if normalized != (row["solicitante"] or ""):
                    conn.execute(
                        "UPDATE tickets SET solicitante = ? WHERE sheet_row_number = ?",
                        (normalized, row["sheet_row_number"]),
                    )

            conn.commit()

    def set_ticket_reason(self, row_number: int, resolution_reason: str) -> bool:
        lock_until = int(time.time()) + 120
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM tickets WHERE sheet_row_number = ?",
                (row_number,),
            ).fetchone()
            if not exists:
                return False

            cursor = conn.execute(
                """
                UPDATE tickets
                SET resolution_reason = ?, status_lock_until = ?
                WHERE sheet_row_number = ?
                """,
                (resolution_reason, lock_until, row_number),
            )
            conn.commit()
        return bool(cursor.rowcount >= 0)

    def get_ticket_reason(self, row_number: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT resolution_reason FROM tickets WHERE sheet_row_number = ?",
                (row_number,),
            ).fetchone()
        if not row:
            return ""
        return str(row["resolution_reason"] or "")

    def get_ticket_status(self, row_number: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM tickets WHERE sheet_row_number = ?",
                (row_number,),
            ).fetchone()
        if not row:
            return ""
        return self._canonical_status(str(row["status"] or ""))

    @staticmethod
    def _canonical_status(status: str) -> str:
        normalized = (status or "").strip().lower()
        if "concl" in normalized:
            return "Concluído"
        if "andamento" in normalized:
            return "Em andamento"
        if not normalized:
            return "Em aberto"
        return status.strip()

    def list_resolution_reasons(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM resolution_reasons ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [row["name"] for row in rows]

    def add_resolution_reason(self, reason: str, note: str = "") -> None:
        value = reason.strip()
        if not value:
            return

        note_value = (note or "").strip()

        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO resolution_reasons (name, note) VALUES (?, ?)",
                (value, note_value),
            )
            conn.commit()

    def remove_resolution_reason(self, reason: str) -> None:
        value = reason.strip()
        if not value:
            return

        with self._connect() as conn:
            conn.execute("DELETE FROM resolution_reasons WHERE name = ?", (value,))
            conn.commit()

    def count_reason_usage(self, reason: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM tickets WHERE resolution_reason = ?",
                (reason,),
            ).fetchone()
        return int(row["total"] if row else 0)

    def clear_reason_from_tickets(self, reason: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE tickets SET resolution_reason = '' WHERE resolution_reason = ?",
                (reason,),
            )
            conn.commit()

    def resolution_reason_usage_map(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT resolution_reason, COUNT(*) AS total
                FROM tickets
                WHERE TRIM(COALESCE(resolution_reason, '')) <> ''
                GROUP BY resolution_reason
                """
            ).fetchall()

        return {row["resolution_reason"]: int(row["total"]) for row in rows}

    def list_resolution_reason_entries(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, note FROM resolution_reasons ORDER BY name COLLATE NOCASE"
            ).fetchall()

        return [
            {
                "name": row["name"],
                "note": row["note"] or "",
            }
            for row in rows
        ]

    def delete_ticket(self, row_number: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM tickets WHERE sheet_row_number = ?", (row_number,))
            conn.commit()

    def shift_row_numbers_after_delete(self, deleted_row_number: int) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sheet_row_number
                FROM tickets
                WHERE sheet_row_number > ?
                ORDER BY sheet_row_number ASC
                """,
                (deleted_row_number,),
            ).fetchall()

            for row in rows:
                current = int(row["sheet_row_number"])
                conn.execute(
                    "UPDATE tickets SET sheet_row_number = ? WHERE sheet_row_number = ?",
                    (current - 1, current),
                )

            conn.commit()

    def list_distinct_locals(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT local
                FROM tickets
                WHERE TRIM(COALESCE(local, '')) <> ''
                ORDER BY local COLLATE NOCASE
                """
            ).fetchall()
        return [row["local"] for row in rows]

    def count_by_local(
        self,
        status_filter: str | None = None,
        local_filter: str | None = None,
    ) -> list[dict[str, int | str]]:
        query = """
            SELECT local, COUNT(*) AS total
            FROM tickets
            WHERE TRIM(COALESCE(local, '')) <> ''
        """
        params: list[str] = []

        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)

        if local_filter:
            query += " AND local = ?"
            params.append(local_filter)

        query += " GROUP BY local ORDER BY total DESC, local ASC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [{"label": row["local"], "total": row["total"]} for row in rows]

    def count_by_resolution_reason(
        self,
        local_filter: str | None = None,
    ) -> list[dict[str, int | str]]:
        query = """
            SELECT resolution_reason, COUNT(*) AS total
            FROM tickets
            WHERE status = 'Concluído'
              AND TRIM(COALESCE(resolution_reason, '')) <> ''
        """
        params: list[str] = []

        if local_filter:
            query += " AND local = ?"
            params.append(local_filter)

        query += " GROUP BY resolution_reason ORDER BY total DESC, resolution_reason ASC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [{"label": row["resolution_reason"], "total": row["total"]} for row in rows]

    def count_by_requester(
        self,
        limit: int = 5,
        local_filter: str | None = None,
    ) -> list[dict[str, int | str]]:
        query = """
            SELECT solicitante, local, COUNT(*) AS total
            FROM tickets
            WHERE TRIM(COALESCE(solicitante, '')) <> ''
        """
        params: list[str | int] = []

        if local_filter:
            query += " AND local = ?"
            params.append(local_filter)

        query += " GROUP BY solicitante, local ORDER BY total DESC, solicitante ASC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [
            {
                "requester": row["solicitante"],
                "local": row["local"] or "--",
                "total": row["total"],
            }
            for row in rows
        ]
