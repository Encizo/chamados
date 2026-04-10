from dataclasses import dataclass


@dataclass
class Ticket:
    row_number: int
    data_hora: str
    local: str
    problema: str
    solicitante: str
    status: str
    resolution_reason: str = ""
