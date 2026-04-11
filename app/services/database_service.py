from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import datetime
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
                    ticket_uid TEXT UNIQUE NOT NULL,
                    sheet_row_number INTEGER,
                    in_sheet INTEGER DEFAULT 1,
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

            self._migrate_tickets_schema_if_needed(conn)

            ticket_columns = conn.execute("PRAGMA table_info(tickets)").fetchall()
            ticket_column_names = {row[1] for row in ticket_columns}
            if "status_lock_until" not in ticket_column_names:
                conn.execute("ALTER TABLE tickets ADD COLUMN status_lock_until INTEGER DEFAULT 0")
            if "in_sheet" not in ticket_column_names:
                conn.execute("ALTER TABLE tickets ADD COLUMN in_sheet INTEGER DEFAULT 1")
            if "sheet_row_number" not in ticket_column_names:
                conn.execute("ALTER TABLE tickets ADD COLUMN sheet_row_number INTEGER")
            if "ticket_uid" not in ticket_column_names:
                conn.execute("ALTER TABLE tickets ADD COLUMN ticket_uid TEXT")

            # Legacy migration from old schema keyed by sheet_row_number
            if "ticket_uid" in ticket_column_names and "sheet_row_number" in ticket_column_names:
                rows = conn.execute(
                    "SELECT id, ticket_uid, data_hora, local, problema, solicitante FROM tickets"
                ).fetchall()
                for row in rows:
                    if row["ticket_uid"]:
                        continue
                    uid = self._build_ticket_uid(
                        data_hora=row["data_hora"] or "",
                        local=row["local"] or "",
                        problema=row["problema"] or "",
                        solicitante=row["solicitante"] or "",
                    )
                    conn.execute("UPDATE tickets SET ticket_uid = ? WHERE id = ?", (uid, row["id"]))

            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_uid ON tickets(ticket_uid)")
            conn.commit()

    def _migrate_tickets_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        info_rows = conn.execute("PRAGMA table_info(tickets)").fetchall()
        if not info_rows:
            return

        by_name = {row[1]: row for row in info_rows}
        sheet_row_notnull = int(by_name.get("sheet_row_number", [None, None, None, 0])[3] or 0) == 1
        needs_uid = "ticket_uid" not in by_name
        needs_in_sheet = "in_sheet" not in by_name

        unique_on_sheet_row = False
        for idx in conn.execute("PRAGMA index_list(tickets)").fetchall():
            # idx format: (seq, name, unique, origin, partial)
            idx_name = idx[1]
            idx_unique = int(idx[2]) == 1
            if not idx_unique:
                continue
            cols = conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
            for col in cols:
                # col format: (seqno, cid, name)
                if str(col[2]) == "sheet_row_number":
                    unique_on_sheet_row = True
                    break
            if unique_on_sheet_row:
                break

        if not (sheet_row_notnull or unique_on_sheet_row or needs_uid or needs_in_sheet):
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_uid TEXT UNIQUE NOT NULL,
                sheet_row_number INTEGER,
                in_sheet INTEGER DEFAULT 1,
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

        old_rows = conn.execute(
            """
            SELECT id, sheet_row_number, data_hora, local, problema, solicitante, status, resolution_reason, status_lock_until, ticket_uid, in_sheet
            FROM tickets
            ORDER BY id ASC
            """
        ).fetchall()

        for row in old_rows:
            raw_uid = row[9] if len(row) > 9 else None
            base_uid = str(raw_uid or "").strip()
            if not base_uid:
                base_uid = self._build_ticket_uid(
                    data_hora=str(row[2] or ""),
                    local=str(row[3] or ""),
                    problema=str(row[4] or ""),
                    solicitante=str(row[5] or ""),
                )

            uid = base_uid
            suffix = 1
            while conn.execute(
                "SELECT 1 FROM tickets_migrated WHERE ticket_uid = ?",
                (uid,),
            ).fetchone():
                suffix += 1
                uid = f"{base_uid}-{suffix}"

            in_sheet = row[10] if len(row) > 10 else 1
            if in_sheet is None:
                in_sheet = 1

            conn.execute(
                """
                INSERT INTO tickets_migrated (
                    id, ticket_uid, sheet_row_number, in_sheet, data_hora, local, problema, solicitante, status, resolution_reason, status_lock_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row[0],
                    uid,
                    row[1],
                    int(in_sheet),
                    row[2] or "",
                    row[3] or "",
                    row[4] or "",
                    row[5] or "",
                    row[6] or "Em aberto",
                    row[7] or "",
                    row[8] or 0,
                ),
            )

        conn.execute("DROP TABLE tickets")
        conn.execute("ALTER TABLE tickets_migrated RENAME TO tickets")

    def upsert_tickets_from_sheet(self, tickets: list[Ticket]) -> None:
        with self._connect() as conn:
            incoming_uids: set[str] = set()

            for ticket in tickets:
                normalized_requester = self._normalize_requester_name(ticket.solicitante)
                ticket_uid = self._build_ticket_uid(
                    data_hora=ticket.data_hora,
                    local=ticket.local,
                    problema=ticket.problema,
                    solicitante=normalized_requester,
                )
                incoming_uids.add(ticket_uid)

                conn.execute(
                    """
                    INSERT INTO tickets (
                        ticket_uid, sheet_row_number, in_sheet, data_hora, local, problema, solicitante, status, resolution_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticket_uid) DO UPDATE SET
                        sheet_row_number=excluded.sheet_row_number,
                        in_sheet=1,
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
                        resolution_reason=tickets.resolution_reason,
                        status_lock_until=CASE
                            WHEN tickets.status_lock_until > CAST(strftime('%s','now') AS INTEGER)
                                 AND excluded.status <> tickets.status
                            THEN tickets.status_lock_until
                            ELSE 0
                        END
                    """,
                    (
                        ticket_uid,
                        ticket.row_number,
                        1,
                        ticket.data_hora,
                        ticket.local,
                        ticket.problema,
                        normalized_requester,
                        ticket.status,
                        "",
                    ),
                )

            if incoming_uids:
                placeholders = ",".join("?" for _ in incoming_uids)
                conn.execute(
                    f"UPDATE tickets SET in_sheet = 0, sheet_row_number = NULL WHERE ticket_uid NOT IN ({placeholders})",
                    tuple(sorted(incoming_uids)),
                )
            else:
                conn.execute("UPDATE tickets SET in_sheet = 0, sheet_row_number = NULL")

            conn.commit()

    def replace_tickets_from_sheet(self, tickets: list[Ticket]) -> None:
        # Keep historical tickets. Just reconcile against latest sheet snapshot.
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
                SELECT id, data_hora, local, problema, solicitante, status, resolution_reason
                FROM tickets
                ORDER BY id DESC
                """
            ).fetchall()

        tickets = [
            Ticket(
                row_number=row["id"],
                data_hora=row["data_hora"] or "",
                local=row["local"] or "",
                problema=row["problema"] or "",
                solicitante=row["solicitante"] or "",
                status=self._canonical_status(row["status"] or "Em aberto"),
                resolution_reason=row["resolution_reason"] or "",
            )
            for row in rows
        ]

        tickets.sort(
            key=lambda ticket: (
                self._parse_ticket_datetime(ticket.data_hora),
                int(ticket.row_number),
            ),
            reverse=True,
        )
        return tickets

    def set_ticket_status(self, row_number: int, status: str, resolution_reason: str) -> None:
        canonical_status = self._canonical_status(status)
        lock_until = int(time.time()) + 120
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tickets
                SET status = ?, resolution_reason = ?, status_lock_until = ?
                WHERE id = ?
                """,
                (canonical_status, resolution_reason, lock_until, row_number),
            )
            conn.commit()

    def normalize_all_requester_names(self) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, solicitante FROM tickets").fetchall()

            for row in rows:
                normalized = self._normalize_requester_name(row["solicitante"] or "")
                if normalized != (row["solicitante"] or ""):
                    conn.execute(
                        "UPDATE tickets SET solicitante = ? WHERE id = ?",
                        (normalized, row["id"]),
                    )

            conn.commit()

    def set_ticket_reason(self, row_number: int, resolution_reason: str) -> bool:
        lock_until = int(time.time()) + 120
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM tickets WHERE id = ?",
                (row_number,),
            ).fetchone()
            if not exists:
                return False

            cursor = conn.execute(
                """
                UPDATE tickets
                SET resolution_reason = ?, status_lock_until = ?
                WHERE id = ?
                """,
                (resolution_reason, lock_until, row_number),
            )
            conn.commit()
        return bool(cursor.rowcount >= 0)

    def get_ticket_reason(self, row_number: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT resolution_reason FROM tickets WHERE id = ?",
                (row_number,),
            ).fetchone()
        if not row:
            return ""
        return str(row["resolution_reason"] or "")

    def get_ticket_status(self, row_number: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM tickets WHERE id = ?",
                (row_number,),
            ).fetchone()
        if not row:
            return ""
        return self._canonical_status(str(row["status"] or ""))

    def get_sheet_row_for_ticket(self, row_number: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sheet_row_number, in_sheet FROM tickets WHERE id = ?",
                (row_number,),
            ).fetchone()
        if not row:
            return None
        if int(row["in_sheet"] or 0) != 1:
            return None
        if row["sheet_row_number"] is None:
            return None
        return int(row["sheet_row_number"])

    def get_ticket_snapshot(self, row_number: int) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT data_hora, local, problema, solicitante
                FROM tickets
                WHERE id = ?
                """,
                (row_number,),
            ).fetchone()
        if not row:
            return None
        return {
            "data_hora": str(row["data_hora"] or ""),
            "local": str(row["local"] or ""),
            "problema": str(row["problema"] or ""),
            "solicitante": str(row["solicitante"] or ""),
        }

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
            conn.execute("DELETE FROM tickets WHERE id = ?", (row_number,))
            conn.commit()

    def shift_row_numbers_after_delete(self, deleted_row_number: int) -> None:
        # No-op with stable local IDs
        return

    def shift_sheet_row_numbers_after_remote_delete(self, deleted_sheet_row: int) -> None:
        if deleted_sheet_row < 2:
            return
        with self._connect() as conn:
            # Two-step shift avoids transient UNIQUE collisions on sheet_row_number.
            offset = 1000000
            conn.execute(
                """
                UPDATE tickets
                SET sheet_row_number = sheet_row_number + ?
                WHERE in_sheet = 1
                  AND sheet_row_number IS NOT NULL
                  AND sheet_row_number > ?
                """,
                (offset, deleted_sheet_row),
            )
            conn.execute(
                """
                UPDATE tickets
                SET sheet_row_number = sheet_row_number - ?
                WHERE in_sheet = 1
                  AND sheet_row_number IS NOT NULL
                  AND sheet_row_number >= ?
                """,
                (offset + 1, deleted_sheet_row + offset + 1),
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
                "label": row["solicitante"],
                "local": row["local"],
                "total": int(row["total"]),
            }
            for row in rows
        ]

    @staticmethod
    def _build_ticket_uid(*, data_hora: str, local: str, problema: str, solicitante: str) -> str:
        payload = "|".join(
            [
                (data_hora or "").strip().lower(),
                (local or "").strip().lower(),
                (problema or "").strip().lower(),
                (solicitante or "").strip().lower(),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_ticket_datetime(raw_value: str) -> datetime:
        text = (raw_value or "").strip()
        if not text:
            return datetime.min

        patterns = (
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        )
        for pattern in patterns:
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
        return datetime.min
