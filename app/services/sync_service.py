from __future__ import annotations

from datetime import datetime, timedelta

from app.services.database_service import DatabaseService
from app.services.sheets_service import SheetsService, SheetsServiceError


class SyncService:
    def __init__(
        self,
        db: DatabaseService,
        sheets: SheetsService,
        interval_seconds: int = 20,
    ) -> None:
        self.db = db
        self.sheets = sheets
        self.interval_seconds = max(5, interval_seconds)
        self._last_success: datetime | None = None

    def maybe_sync(self) -> tuple[bool, str | None]:
        now = datetime.now()
        if self._last_success and now - self._last_success < timedelta(seconds=self.interval_seconds):
            return False, None

        return self.force_sync()

    def force_sync(self) -> tuple[bool, str | None]:
        try:
            tickets = self.sheets.fetch_tickets()
            self.db.upsert_tickets_from_sheet(tickets)
            self._last_success = datetime.now()
            return True, None
        except SheetsServiceError as exc:
            return False, str(exc)
