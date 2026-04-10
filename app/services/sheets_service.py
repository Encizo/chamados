from __future__ import annotations

import json

from google.auth.exceptions import GoogleAuthError
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.models.ticket import Ticket


class SheetsServiceError(Exception):
    pass


class SheetsService:
    def __init__(self, service_account_file: str, sheet_id: str, sheet_range: str) -> None:
        self.service_account_file = service_account_file
        self.sheet_id = sheet_id
        self.sheet_range = sheet_range

    def fetch_tickets(self) -> list[Ticket]:
        if not self.service_account_file or not self.sheet_id:
            raise SheetsServiceError(
                "Configure GOOGLE_SERVICE_ACCOUNT_FILE e GOOGLE_SHEETS_ID no ambiente."
            )

        service = self._build_client(readonly=True)

        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=self.sheet_id, range=self.sheet_range)
                .execute()
            )
        except HttpError as exc:
            status_code = getattr(exc.resp, "status", "desconhecido")
            reason = exc.reason or "erro de permissao"

            details = ""
            if getattr(exc, "content", None):
                try:
                    payload = json.loads(exc.content.decode("utf-8"))
                    details = payload.get("error", {}).get("message", "")
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                    details = ""

            if details:
                message = f"Google Sheets API ({status_code}): {details}"
            else:
                message = f"Google Sheets API ({status_code}): {reason}"

            raise SheetsServiceError(message) from exc

        values = result.get("values", [])

        if not values or len(values) == 1:
            return []

        data_rows = values[1:]
        tickets: list[Ticket] = []

        for index, row in enumerate(data_rows, start=2):
            data_hora = row[0] if len(row) > 0 else ""
            local = row[1] if len(row) > 1 else ""
            problema = row[2] if len(row) > 2 else ""
            solicitante = row[3] if len(row) > 3 else ""
            status = row[4] if len(row) > 4 else ""
            status = self._normalize_status(status)
            solicitante = self._normalize_requester_name(solicitante)

            tickets.append(
                Ticket(
                    row_number=index,
                    data_hora=data_hora,
                    local=local,
                    problema=problema,
                    solicitante=solicitante,
                    status=status,
                )
            )

        tickets.sort(key=lambda ticket: ticket.row_number, reverse=True)

        return tickets

    def update_ticket_status(self, row_number: int, status: str) -> None:
        if row_number < 2:
            raise SheetsServiceError("Linha de chamado invalida para atualizacao.")

        service = self._build_client(readonly=False)
        normalized_status = self._status_to_sheet_value(status)
        sheet_name = self._get_sheet_name()
        update_range = f"{sheet_name}!E{row_number}"

        try:
            service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=update_range,
                valueInputOption="RAW",
                body={"values": [[normalized_status]]},
            ).execute()
        except HttpError as exc:
            status_code = getattr(exc.resp, "status", "desconhecido")
            reason = exc.reason or "erro ao atualizar status"
            raise SheetsServiceError(f"Google Sheets API ({status_code}): {reason}") from exc

    def delete_ticket_row(self, row_number: int) -> None:
        if row_number < 2:
            raise SheetsServiceError("Linha de chamado invalida para exclusao.")

        service = self._build_client(readonly=False)
        sheet_id = self._get_sheet_gid(service)

        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={
                    "requests": [
                        {
                            "deleteDimension": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "dimension": "ROWS",
                                    "startIndex": row_number - 1,
                                    "endIndex": row_number,
                                }
                            }
                        }
                    ]
                },
            ).execute()
        except HttpError as exc:
            status_code = getattr(exc.resp, "status", "desconhecido")
            reason = exc.reason or "erro ao excluir chamado"
            raise SheetsServiceError(f"Google Sheets API ({status_code}): {reason}") from exc

    def _build_client(self, readonly: bool):
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        if not readonly:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        try:
            credentials = Credentials.from_service_account_file(
                self.service_account_file,
                scopes=scopes,
            )
            return build("sheets", "v4", credentials=credentials, cache_discovery=False)
        except OSError as exc:
            raise SheetsServiceError(
                "Nao foi possivel ler o arquivo da conta de servico."
            ) from exc
        except GoogleAuthError as exc:
            raise SheetsServiceError(
                "Falha na autenticacao com a conta de servico do Google."
            ) from exc

    def _get_sheet_name(self) -> str:
        return self.sheet_range.split("!", maxsplit=1)[0]

    def _get_sheet_title(self) -> str:
        return self._get_sheet_name().strip("'\"")

    def _get_sheet_gid(self, service) -> int:
        meta = service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
        title = self._get_sheet_title()
        for sheet in meta.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == title:
                return int(props.get("sheetId"))

        raise SheetsServiceError("Aba configurada nao encontrada para exclusao.")

    @staticmethod
    def _status_to_sheet_value(status: str) -> str:
        normalized = (status or "").strip().lower()
        if "concl" in normalized:
            return "CONCLUÍDO"
        if "andamento" in normalized:
            return "EM ANDAMENTO"
        return ""

    @staticmethod
    def _normalize_status(value: str) -> str:
        normalized = (value or "").strip().lower()

        if not normalized:
            return "Em aberto"
        if "concl" in normalized:
            return "Concluído"
        if "andamento" in normalized:
            return "Em andamento"

        return value.strip()

    @staticmethod
    def _normalize_requester_name(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""

        words = [word for word in text.split() if word]
        return " ".join(word[:1].upper() + word[1:].lower() for word in words)
