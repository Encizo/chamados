from __future__ import annotations

import json
from io import BytesIO
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String

from app.services.database_service import DatabaseService
from app.services.sheets_service import SheetsService, SheetsServiceError
from app.services.auth_service import AuthService
from app.theme import PALETTES, resolve_palette


ticket_bp = Blueprint("tickets", __name__)
_sheet_write_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sheet-write")


def _auth_service() -> AuthService:
    return AuthService(current_app.config["DATABASE_PATH"])


def _is_authenticated() -> bool:
    return bool(session.get("is_admin_authenticated"))


def _ensure_bootstrap_admin() -> None:
    auth = _auth_service()
    if auth.has_any_admin():
        return
    bootstrap_user = (current_app.config.get("APP_BOOTSTRAP_ADMIN_USER", "admin") or "admin").strip()
    bootstrap_pass = (current_app.config.get("APP_BOOTSTRAP_ADMIN_PASS", "admin123") or "admin123").strip()
    auth.create_or_update_admin(bootstrap_user, bootstrap_pass)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        _ensure_bootstrap_admin()
        if _is_authenticated():
            return view(*args, **kwargs)
        next_url = request.path
        if request.query_string:
            next_url += f"?{request.query_string.decode('utf-8', errors='ignore')}"
        return redirect(url_for("tickets.login_page", next=next_url))

    return wrapped


def _schedule_sheet_write(
    *,
    service_account_file: str,
    sheet_id: str,
    sheet_range: str,
    action: str,
    row_number: int,
    status: str = "",
) -> None:
    def worker() -> None:
        service = SheetsService(
            service_account_file=service_account_file,
            sheet_id=sheet_id,
            sheet_range=sheet_range,
        )
        if action == "status":
            service.update_ticket_status(row_number=row_number, status=status)
            return
        if action == "delete":
            service.delete_ticket_row(row_number=row_number)

    _sheet_write_executor.submit(worker)


def _config_file_path() -> Path:
    return Path(current_app.root_path).parent / ".env"


def _read_env_file() -> dict[str, str]:
    env_path = _config_file_path()
    values: dict[str, str] = {}

    if not env_path.exists():
        return values

    for line in env_path.read_text(encoding="utf-8").splitlines():
        content = line.strip()
        if not content or content.startswith("#") or "=" not in content:
            continue
        key, value = content.split("=", maxsplit=1)
        values[key.strip()] = value.strip()

    return values


def _write_env_file(values: dict[str, str]) -> None:
    env_path = _config_file_path()
    lines = [f"{key}={value}" for key, value in values.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_service_account_path() -> Path:
    configured_path = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not configured_path:
        return Path(current_app.root_path).parent / "credenciais" / "service-account.json"

    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate

    return Path(current_app.root_path).parent / candidate


def _detect_service_email() -> str | None:
    try:
        service_file = _resolve_service_account_path()
        if not service_file.exists():
            return None

        payload = json.loads(service_file.read_text(encoding="utf-8"))
        return payload.get("client_email")
    except (OSError, json.JSONDecodeError):
        return None


def _load_dashboard_data() -> tuple[list, str | None, dict[str, int]]:
    db = DatabaseService(current_app.config["DATABASE_PATH"])
    error = None
    tickets = db.list_tickets()

    status_summary = {
        "total": len(tickets),
        "aberto": sum(1 for ticket in tickets if ticket.status == "Em aberto"),
        "andamento": sum(1 for ticket in tickets if ticket.status == "Em andamento"),
        "concluido": sum(1 for ticket in tickets if ticket.status == "Concluído"),
    }

    return tickets, error, status_summary


def _load_branding() -> dict[str, str]:
    return {
        "brand_short": current_app.config.get("APP_BRAND_SHORT", "SEMSAU"),
        "brand_name": current_app.config.get("APP_BRAND_NAME", "Painel de Chamados"),
        "org_name": current_app.config.get("APP_ORG_NAME", "Secretaria Municipal de Saude"),
        "tickets_title": current_app.config.get(
            "APP_TICKETS_TITLE", "Painel de Chamados TI - SEMSAU"
        ),
        "dashboard_title": current_app.config.get("APP_DASHBOARD_TITLE", "Dashboard SEMSAU IT"),
        "tickets_subtitle": current_app.config.get(
            "APP_TICKETS_SUBTITLE",
            "Atendimento em tempo real integrado ao Google Forms e Google Sheets.",
        ),
    }


def _paginate_tickets(tickets: list, page: int, page_size: int) -> tuple[list, dict[str, int]]:
    total = len(tickets)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = max(1, min(page, total_pages))
    start = (current_page - 1) * page_size
    end = start + page_size
    items = tickets[start:end]
    meta = {
        "page": current_page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": total_pages,
    }
    return items, meta


def _parse_ticket_date(raw_value: str) -> date | None:
    text = (raw_value or "").strip()
    if not text:
        return None

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
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue

    return None


def _theme_color(name: str, fallback: str) -> str:
    palette = current_app.config.get("APP_THEME_VARS", {}) or {}
    return str(palette.get(name, fallback))


def _load_local_colors() -> dict[str, str]:
    raw = current_app.config.get("APP_LOCAL_COLORS_JSON", "{}")
    if not isinstance(raw, str):
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    valid: dict[str, str] = {}
    for key, value in payload.items():
        local_name = str(key or "").strip()
        color = str(value or "").strip()
        if not local_name or not color:
            continue
        if len(color) == 7 and color.startswith("#"):
            valid[local_name] = color
    return valid


def _build_analytics_payload(
    db: DatabaseService,
    *,
    period: str,
    selected_locals: list[str] | None = None,
    detail_local: str = "",
    include_all_details: bool = False,
) -> dict:
    today = date.today()
    if period not in {"all", "week", "30d", "month", "year"}:
        period = "30d"

    start_date = None
    if period == "week":
        start_date = today - timedelta(days=today.weekday())
    elif period == "30d":
        start_date = today - timedelta(days=29)
    elif period == "month":
        start_date = today.replace(day=1)
    elif period == "year":
        start_date = today.replace(month=1, day=1)

    all_tickets = db.list_tickets()
    period_tickets = []
    for ticket in all_tickets:
        parsed_date = _parse_ticket_date(ticket.data_hora)
        if not parsed_date:
            continue
        if start_date is not None and not (start_date <= parsed_date <= today):
            continue
        period_tickets.append((ticket, parsed_date))

    selected_locals_set = set(selected_locals or [])
    filtered = []
    for ticket, parsed_date in period_tickets:
        if selected_locals_set and ticket.local not in selected_locals_set:
            continue
        filtered.append((ticket, parsed_date))

    local_counter = Counter(ticket.local for ticket, _ in filtered if ticket.local)
    local_stats = [
        {"label": label, "total": total}
        for label, total in sorted(local_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    reason_counter = Counter(
        (ticket.resolution_reason if ticket.resolution_reason else "Sem motivo")
        for ticket, _ in filtered
        if ticket.status == "Concluído"
    )
    reason_stats = [
        {"label": label, "total": total}
        for label, total in sorted(reason_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    requester_counter = Counter(ticket.solicitante for ticket, _ in filtered if ticket.solicitante)
    requester_local_map: dict[str, str] = {}
    for ticket, _ in filtered:
        if ticket.solicitante and ticket.solicitante not in requester_local_map:
            requester_local_map[ticket.solicitante] = ticket.local or "--"

    top_requesters = [
        {
            "requester": requester,
            "local": requester_local_map.get(requester, "--"),
            "total": total,
        }
        for requester, total in sorted(
            requester_counter.items(), key=lambda item: (-item[1], item[0])
        )[:10]
    ]

    total_calls = len(filtered)
    total_concluded = sum(reason_counter.values())
    top_local = local_stats[0]["label"] if local_stats else "--"
    distinct_locals = sorted({ticket.local for ticket, _ in filtered if ticket.local}, key=str.lower)

    pie_source = reason_stats[:4]
    if len(reason_stats) > 4:
        pie_source.append(
            {
                "label": "Outros",
                "total": sum(item["total"] for item in reason_stats[4:]),
            }
        )

    pie_colors = [
        _theme_color("primary-deep", "#00478d"),
        _theme_color("accent-open", "#48626e"),
        _theme_color("accent-warn", "#793100"),
        _theme_color("primary", "#005eb8"),
        _theme_color("accent-ok", "#727783"),
    ]
    pie_total = sum(item["total"] for item in pie_source) or 1
    reason_pie = []
    offset = 0
    for idx, item in enumerate(pie_source):
        pct = round((item["total"] * 100) / pie_total, 2)
        reason_pie.append(
            {
                "label": item["label"],
                "total": item["total"],
                "percent": pct,
                "dasharray": f"{pct}, 100",
                "dashoffset": f"-{offset}",
                "color": pie_colors[idx % len(pie_colors)],
            }
        )
        offset += pct

    weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    counts = defaultdict(int)
    for _, parsed_date in filtered:
        counts[parsed_date.weekday()] += 1
    volume_series: list[dict[str, int | str]] = [
        {"label": weekday_labels[i], "total": counts[i]} for i in range(7)
    ]

    volume_max = max([item["total"] for item in volume_series] + [1])
    period_labels = {
        "all": "Tempo total",
        "week": "Esta semana",
        "30d": "Ultimos 30 dias",
        "month": "Mes atual",
        "year": "Ano atual",
    }

    reason_note_map = {entry["name"]: entry["note"] for entry in db.list_resolution_reason_entries()}
    detail_local_options = distinct_locals
    if detail_local and detail_local not in detail_local_options:
        detail_local = ""

    detailed_tickets = []
    if include_all_details:
        for ticket, _ in filtered:
            reason_label = ticket.resolution_reason if ticket.resolution_reason else "Sem motivo"
            detailed_tickets.append(
                {
                    "data_hora": ticket.data_hora,
                    "local": ticket.local,
                    "solicitante": ticket.solicitante,
                    "problema": ticket.problema,
                    "status": ticket.status,
                    "motivo": reason_label,
                    "observacao": reason_note_map.get(ticket.resolution_reason, "") if ticket.resolution_reason else "",
                }
            )
    elif detail_local:
        for ticket, _ in filtered:
            if ticket.local != detail_local:
                continue
            reason_label = ticket.resolution_reason if ticket.resolution_reason else "Sem motivo"
            detailed_tickets.append(
                {
                    "data_hora": ticket.data_hora,
                    "local": ticket.local,
                    "solicitante": ticket.solicitante,
                    "problema": ticket.problema,
                    "status": ticket.status,
                    "motivo": reason_label,
                    "observacao": reason_note_map.get(ticket.resolution_reason, "") if ticket.resolution_reason else "",
                }
            )

    return {
        "period": period,
        "period_label": period_labels[period],
        "local_stats": local_stats,
        "reason_stats": reason_stats,
        "reason_pie": reason_pie,
        "reason_pie_total": pie_total,
        "top_requesters": top_requesters,
        "kpi_total": total_calls,
        "kpi_concluded": total_concluded,
        "kpi_top_local": top_local,
        "kpi_local_count": len(distinct_locals),
        "volume_series": volume_series,
        "volume_max": volume_max,
        "detail_local": detail_local,
        "detail_local_options": detail_local_options,
        "detailed_tickets": detailed_tickets,
    }


@ticket_bp.route("/")
@admin_required
def dashboard():
    tickets, error, status_summary = _load_dashboard_data()
    branding = _load_branding()
    credentials_ok = _resolve_service_account_path().exists()

    health = {
        "credentials": "OK" if credentials_ok else "Nao configuradas",
        "api": "OK" if not error else "Falha",
        "last_sync": datetime.now().strftime("%d/%m/%Y %H:%M:%S") if not error else "--",
        "error": error or "Sem erros recentes.",
        "service_email": _detect_service_email(),
    }

    latest_tickets = tickets[:5]
    local_counter = Counter(ticket.local for ticket in tickets if ticket.local)
    dashboard_local_stats = [
        {"label": label, "total": total}
        for label, total in sorted(local_counter.items(), key=lambda item: (-item[1], item[0]))[:6]
    ]
    local_max = dashboard_local_stats[0]["total"] if dashboard_local_stats else 1

    return render_template(
        "dashboard.html",
        tickets=tickets,
        error=error,
        status_summary=status_summary,
        branding=branding,
        health=health,
        latest_tickets=latest_tickets,
        dashboard_local_stats=dashboard_local_stats,
        dashboard_local_max=local_max,
        local_color_map=_load_local_colors(),
    )


@ticket_bp.route("/chamados")
@admin_required
def tickets_page():
    page = request.args.get("page", default=1, type=int) or 1
    page_size = 20
    tickets, error, status_summary = _load_dashboard_data()
    paged_tickets, pagination = _paginate_tickets(tickets, page=page, page_size=page_size)
    branding = _load_branding()
    db = DatabaseService(current_app.config["DATABASE_PATH"])
    return render_template(
        "tickets.html",
        tickets=paged_tickets,
        error=error,
        status_summary=status_summary,
        branding=branding,
        resolution_reasons=db.list_resolution_reasons(),
        pagination=pagination,
        local_color_map=_load_local_colors(),
    )


@ticket_bp.route("/chamados/monitor")
@admin_required
def tickets_monitor_page():
    branding = _load_branding()
    return render_template(
        "tickets_monitor.html",
        branding=branding,
        theme_vars=current_app.config.get("APP_THEME_VARS", {}),
        local_color_map=_load_local_colors(),
    )


@ticket_bp.route("/api/tickets")
@admin_required
def tickets_api():
    page = request.args.get("page", default=1, type=int) or 1
    page_size = request.args.get("page_size", default=20, type=int) or 20
    tickets, error, status_summary = _load_dashboard_data()
    paged_tickets, pagination = _paginate_tickets(tickets, page=page, page_size=page_size)
    return jsonify(
        {
            "tickets": [
                {
                    "row_number": ticket.row_number,
                    "data_hora": ticket.data_hora,
                    "local": ticket.local,
                    "problema": ticket.problema,
                    "solicitante": ticket.solicitante,
                    "status": ticket.status,
                    "resolution_reason": ticket.resolution_reason,
                }
                for ticket in paged_tickets
            ],
            "status_summary": status_summary,
            "error": error,
            "pagination": pagination,
        }
    )


@ticket_bp.route("/analytics")
@admin_required
def analytics_page():
    db = DatabaseService(current_app.config["DATABASE_PATH"])
    branding = _load_branding()

    period = request.args.get("period", "30d").strip().lower()
    detail_local = request.args.get("detail_local", "").strip()
    selected_locals = request.args.getlist("locals")
    payload = _build_analytics_payload(
        db,
        period=period,
        selected_locals=selected_locals,
        detail_local=detail_local,
    )

    return render_template(
        "analytics.html",
        branding=branding,
        selected_locals=selected_locals,
        **payload,
    )


@ticket_bp.route("/analytics/export", methods=["POST"])
@admin_required
def export_analytics_pdf():
    db = DatabaseService(current_app.config["DATABASE_PATH"])

    period = request.form.get("period", "30d").strip().lower()
    selected_locals = [value for value in request.form.getlist("locals") if value]
    sections = set(request.form.getlist("sections"))
    detail_local = ""

    if "all_locals" in request.form:
        selected_locals = []

    payload = _build_analytics_payload(
        db,
        period=period,
        selected_locals=selected_locals,
        detail_local=detail_local,
        include_all_details=("individual" in sections),
    )

    if not sections:
        sections = {
            "volume",
            "reasons",
            "top_requesters",
            "local_volume",
            "individual",
        }

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=30, bottomMargin=26)
    styles = getSampleStyleSheet()

    pdf_primary = _theme_color("primary", "#005eb8")
    pdf_primary_deep = _theme_color("primary-deep", "#003b78")
    pdf_line = _theme_color("line", "#c9d7eb")
    pdf_primary_soft = _theme_color("primary-soft", "#eaf2ff")
    pdf_surface_soft = _theme_color("surface-soft", "#f2f6fb")
    pdf_open = _theme_color("accent-open", "#48626e")
    pdf_warn = _theme_color("accent-warn", "#793100")
    pdf_ok = _theme_color("accent-ok", "#0f7c4a")
    pdf_muted = _theme_color("muted", "#5b6e7f")
    h_style = ParagraphStyle(
        "HeadingCard",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor(pdf_primary_deep),
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodySmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
    )
    story = []

    branding = _load_branding()
    report_title = f"{branding.get('brand_short', 'SEMSAU')} - Relatorio de Analytics"
    story.append(Paragraph(report_title, styles["Title"]))
    story.append(Paragraph(f"Periodo: {payload['period_label']}", body_style))
    if selected_locals:
        story.append(Paragraph("Locais filtrados: " + ", ".join(selected_locals), body_style))
    else:
        story.append(Paragraph("Locais: Todos", body_style))
    story.append(Spacer(1, 12))

    summary_data = [
        ["Total de chamados", str(payload["kpi_total"])],
        ["Concluidos", str(payload["kpi_concluded"])],
        ["Local com maior volume", str(payload["kpi_top_local"])],
        ["Locais monitorados", str(payload["kpi_local_count"])],
    ]
    summary_table = Table(summary_data, colWidths=[240, 240])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(pdf_primary_soft)),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(pdf_line)),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 14))

    def append_table(title: str, headers: list[str], rows: list[list], col_widths=None) -> None:
        if title:
            story.append(Paragraph(title, h_style))
        if not rows:
            story.append(Paragraph("Sem dados para este recorte.", body_style))
            story.append(Spacer(1, 10))
            return
        table = Table([headers] + rows, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(pdf_surface_soft)),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(pdf_line)),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))

    def append_bar_chart(title: str, labels: list[str], values: list[int], color_hex: str) -> None:
        story.append(Paragraph(title, h_style))
        if not values:
            story.append(Paragraph("Sem dados para este grafico.", body_style))
            story.append(Spacer(1, 10))
            return

        width = 500
        height = 210
        drawing = Drawing(width, height)
        chart = VerticalBarChart()
        chart.x = 38
        chart.y = 28
        chart.height = 145
        chart.width = 420
        chart.data = [values]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(max(values), 1)
        chart.valueAxis.valueStep = max(1, int(chart.valueAxis.valueMax / 5) or 1)
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.angle = 45
        chart.categoryAxis.labels.dy = -16
        chart.categoryAxis.labels.fontSize = 7
        chart.bars[0].fillColor = colors.HexColor(color_hex)
        chart.bars[0].strokeColor = colors.HexColor(color_hex)
        drawing.add(chart)
        drawing.add(
            String(
                38,
                186,
                "Quantidade de chamados",
                fontName="Helvetica",
                fontSize=8,
                fillColor=colors.HexColor(pdf_muted),
            )
        )
        story.append(drawing)
        story.append(Spacer(1, 8))

    def append_pie_chart(title: str, labels: list[str], values: list[int]) -> None:
        story.append(Paragraph(title, h_style))
        if not values:
            story.append(Paragraph("Sem dados para este grafico.", body_style))
            story.append(Spacer(1, 10))
            return

        drawing = Drawing(500, 220)
        pie = Pie()
        pie.x = 40
        pie.y = 20
        pie.width = 170
        pie.height = 170
        pie.data = values
        pie.labels = [""] * len(labels)
        palette = [
            colors.HexColor(pdf_primary_deep),
            colors.HexColor(pdf_open),
            colors.HexColor(pdf_warn),
            colors.HexColor(pdf_primary),
            colors.HexColor(pdf_ok),
            colors.HexColor(pdf_muted),
        ]
        for idx in range(len(values)):
            pie.slices[idx].fillColor = palette[idx % len(palette)]
        pie.slices.strokeWidth = 0.5
        pie.slices.strokeColor = colors.white
        drawing.add(pie)

        legend_y = 180
        for idx, label in enumerate(labels):
            color = palette[idx % len(palette)]
            item_y = legend_y - (idx * 14)
            drawing.add(String(245, item_y, "■", fontName="Helvetica-Bold", fontSize=10, fillColor=color))
            drawing.add(
                String(
                    258,
                    item_y,
                    f"{label} ({values[idx]})",
                    fontName="Helvetica",
                    fontSize=8,
                    fillColor=colors.HexColor(_theme_color("ink", "#334155")),
                )
            )

        story.append(drawing)
        story.append(Spacer(1, 8))

    if "volume" in sections:
        volume_labels = [str(item["label"]) for item in payload["volume_series"]]
        volume_values = [int(item["total"]) for item in payload["volume_series"]]
        append_bar_chart("Volume por Dia da Semana", volume_labels, volume_values, pdf_primary_deep)

    if "reasons" in sections:
        reason_labels = [str(item["label"]) for item in payload["reason_stats"]]
        reason_values = [int(item["total"]) for item in payload["reason_stats"]]
        append_pie_chart("Motivos de Conclusao", reason_labels, reason_values)

    if "local_volume" in sections:
        local_labels = [str(item["label"]) for item in payload["local_stats"][:10]]
        local_values = [int(item["total"]) for item in payload["local_stats"][:10]]
        append_bar_chart("Volume por Localidade", local_labels, local_values, pdf_primary)
        append_table(
            "Resumo por Localidade",
            ["Local", "Chamados"],
            [[str(item["label"]), str(item["total"])] for item in payload["local_stats"][:20]],
            col_widths=[360, 120],
        )

    if "top_requesters" in sections:
        append_table(
            "Top Solicitantes",
            ["Solicitante", "Local", "Chamados"],
            [
                [str(item["requester"]), str(item["local"]), str(item["total"])]
                for item in payload["top_requesters"]
            ],
            col_widths=[220, 180, 80],
        )

    if "individual" in sections:
        story.append(Paragraph("Analise Individual por Local", h_style))
        if not payload["detailed_tickets"]:
            story.append(Paragraph("Sem dados para este recorte.", body_style))
            story.append(Spacer(1, 10))
        else:
            grouped = defaultdict(list)
            for item in payload["detailed_tickets"]:
                grouped[item["local"] or "Sem local"].append(item)

            for local_name in sorted(grouped.keys(), key=str.lower):
                rows = []
                for item in grouped[local_name]:
                    rows.append(
                        [
                            Paragraph(str(item["data_hora"]).replace(" ", "<br/>", 1), body_style),
                            Paragraph(str(local_name), body_style),
                            Paragraph(str(item["solicitante"]), body_style),
                            Paragraph(f"{item['status']} / {item['motivo']}", body_style),
                            Paragraph(
                                f"Chamado: {item['problema'] or '-'}<br/>Obs. motivo: {item['observacao'] or '-'}",
                                body_style,
                            ),
                        ]
                    )

                append_table(
                    "",
                    ["Data", "Local", "Solicitante", "Status/Motivo", "Detalhes"],
                    rows,
                    col_widths=[64, 72, 84, 96, 147],
                )

    doc.build(story)
    buffer.seek(0)
    filename = f"analytics_{payload['period']}.pdf"
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@ticket_bp.route("/configuracoes", methods=["GET", "POST"])
@admin_required
def settings_page():
    db = DatabaseService(current_app.config["DATABASE_PATH"])
    message = None
    message_type = "success"

    if request.method == "POST":
        values = _read_env_file()
        sheet_id = request.form.get("google_sheets_id", "").strip()
        sheet_range = request.form.get("google_sheets_range", "").strip()
        app_brand_short = request.form.get("app_brand_short", "").strip()
        app_brand_name = request.form.get("app_brand_name", "").strip()
        app_org_name = request.form.get("app_org_name", "").strip()
        app_tickets_title = request.form.get("app_tickets_title", "").strip()
        app_dashboard_title = request.form.get("app_dashboard_title", "").strip()
        app_tickets_subtitle = request.form.get("app_tickets_subtitle", "").strip()
        app_theme_palette = request.form.get("app_theme_palette", "").strip().lower()
        local_color_names = request.form.getlist("local_color_name")
        local_color_values = request.form.getlist("local_color_value")
        new_reason = request.form.get("new_resolution_reason", "").strip()
        new_reason_note = request.form.get("new_resolution_reason_note", "").strip()
        remove_reason = request.form.get("remove_resolution_reason", "").strip()
        service_file = request.files.get("service_account_file")

        if sheet_id:
            values["GOOGLE_SHEETS_ID"] = sheet_id
            current_app.config["GOOGLE_SHEETS_ID"] = sheet_id

        if sheet_range:
            values["GOOGLE_SHEETS_RANGE"] = sheet_range
            current_app.config["GOOGLE_SHEETS_RANGE"] = sheet_range

        if app_brand_short:
            values["APP_BRAND_SHORT"] = app_brand_short
            current_app.config["APP_BRAND_SHORT"] = app_brand_short
        if app_brand_name:
            values["APP_BRAND_NAME"] = app_brand_name
            current_app.config["APP_BRAND_NAME"] = app_brand_name
        if app_org_name:
            values["APP_ORG_NAME"] = app_org_name
            current_app.config["APP_ORG_NAME"] = app_org_name
        if app_tickets_title:
            values["APP_TICKETS_TITLE"] = app_tickets_title
            current_app.config["APP_TICKETS_TITLE"] = app_tickets_title
        if app_dashboard_title:
            values["APP_DASHBOARD_TITLE"] = app_dashboard_title
            current_app.config["APP_DASHBOARD_TITLE"] = app_dashboard_title
        if app_tickets_subtitle:
            values["APP_TICKETS_SUBTITLE"] = app_tickets_subtitle
            current_app.config["APP_TICKETS_SUBTITLE"] = app_tickets_subtitle
        if app_theme_palette:
            resolved_key, resolved_palette = resolve_palette(app_theme_palette)
            values["APP_THEME_PALETTE"] = resolved_key
            current_app.config["APP_THEME_PALETTE"] = resolved_key
            current_app.config["APP_THEME_VARS"] = resolved_palette["vars"]

        color_map: dict[str, str] = {}
        for idx, local_name in enumerate(local_color_names):
            name = (local_name or "").strip()
            color = (local_color_values[idx] if idx < len(local_color_values) else "").strip()
            if not name or not color:
                continue
            if len(color) == 7 and color.startswith("#"):
                color_map[name] = color
        values["APP_LOCAL_COLORS_JSON"] = json.dumps(color_map, ensure_ascii=True, separators=(",", ":"))
        current_app.config["APP_LOCAL_COLORS_JSON"] = values["APP_LOCAL_COLORS_JSON"]

        if service_file and service_file.filename:
            if not service_file.filename.lower().endswith(".json"):
                message = "Arquivo invalido. Envie um JSON de Service Account."
                message_type = "error"
            else:
                service_path = Path(current_app.root_path).parent / "credenciais" / "service-account.json"
                service_path.parent.mkdir(parents=True, exist_ok=True)
                service_file.save(service_path)
                values["GOOGLE_SERVICE_ACCOUNT_FILE"] = "credenciais/service-account.json"
                current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"] = "credenciais/service-account.json"

        if message is None:
            _write_env_file(values)
            if new_reason:
                db.add_resolution_reason(new_reason, note=new_reason_note)
                message = "Motivo adicionado com sucesso."
                message_type = "success"
            if remove_reason:
                db.clear_reason_from_tickets(remove_reason)
                db.remove_resolution_reason(remove_reason)
                message = "Motivo removido com sucesso."
                message_type = "error"
            if not new_reason and not remove_reason:
                message = "Configuracoes salvas com sucesso."

    service_email = _detect_service_email()
    current_values = {
        "service_account_file": current_app.config.get("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
        "google_sheets_id": current_app.config.get("GOOGLE_SHEETS_ID", ""),
        "google_sheets_range": current_app.config.get("GOOGLE_SHEETS_RANGE", ""),
        "app_brand_short": current_app.config.get("APP_BRAND_SHORT", "SEMSAU"),
        "app_brand_name": current_app.config.get("APP_BRAND_NAME", "Painel de Chamados"),
        "app_org_name": current_app.config.get("APP_ORG_NAME", "Secretaria Municipal de Saude"),
        "app_tickets_title": current_app.config.get(
            "APP_TICKETS_TITLE", "Painel de Chamados TI - SEMSAU"
        ),
        "app_dashboard_title": current_app.config.get("APP_DASHBOARD_TITLE", "Dashboard SEMSAU IT"),
        "app_tickets_subtitle": current_app.config.get(
            "APP_TICKETS_SUBTITLE",
            "Atendimento em tempo real integrado ao Google Forms e Google Sheets.",
        ),
        "app_theme_palette": current_app.config.get("APP_THEME_PALETTE", "azul-tech"),
        "app_local_colors_json": current_app.config.get("APP_LOCAL_COLORS_JSON", "{}"),
    }

    local_color_map = _load_local_colors()
    local_options = db.list_distinct_locals()
    for local_name in sorted(local_color_map.keys(), key=str.lower):
        if local_name not in local_options:
            local_options.append(local_name)

    return render_template(
        "settings.html",
        message=message,
        message_type=message_type,
        values=current_values,
        service_email=service_email,
        theme_palettes=[
            {
                "key": key,
                "name": payload["name"],
                "description": payload["description"],
                "colors": payload["colors"],
            }
            for key, payload in PALETTES.items()
        ],
        resolution_reasons=db.list_resolution_reasons(),
        resolution_reason_entries=db.list_resolution_reason_entries(),
        reason_usage_map=db.resolution_reason_usage_map(),
        local_options=local_options,
        local_color_map=local_color_map,
    )


@ticket_bp.route("/configuracoes/testar", methods=["POST"])
@admin_required
def test_connection():
    service = SheetsService(
        service_account_file=current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
        sheet_id=current_app.config["GOOGLE_SHEETS_ID"],
        sheet_range=current_app.config["GOOGLE_SHEETS_RANGE"],
    )

    try:
        tickets = service.fetch_tickets()
        return jsonify(
            {
                "ok": True,
                "message": f"Conexao OK. {len(tickets)} chamados lidos.",
            }
        )
    except SheetsServiceError as exc:
        return jsonify({"ok": False, "message": str(exc)})


@ticket_bp.route("/status/<int:row_number>", methods=["POST"])
@admin_required
def update_status(row_number: int):
    db = DatabaseService(current_app.config["DATABASE_PATH"])

    status = request.form.get("status", "").strip()
    resolution_reason = request.form.get("resolution_reason", "").strip()
    if not resolution_reason:
        resolution_reason = db.get_ticket_reason(row_number)

    error = None
    try:
        sheet_row = db.get_sheet_row_for_ticket(row_number)
        db.set_ticket_status(
            row_number=row_number,
            status=status,
            resolution_reason=resolution_reason,
        )
        if sheet_row:
            _schedule_sheet_write(
                service_account_file=current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
                sheet_id=current_app.config["GOOGLE_SHEETS_ID"],
                sheet_range=current_app.config["GOOGLE_SHEETS_RANGE"],
                action="status",
                row_number=sheet_row,
                status=status,
            )
    except Exception as exc:
        error = str(exc)

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": error is None, "error": error})

    tickets, dashboard_error, status_summary = _load_dashboard_data()
    paged_tickets, pagination = _paginate_tickets(tickets, page=1, page_size=20)
    if error and not dashboard_error:
        dashboard_error = error

    return render_template(
        "tickets.html",
        tickets=paged_tickets,
        error=dashboard_error,
        status_summary=status_summary,
        branding=_load_branding(),
        resolution_reasons=db.list_resolution_reasons(),
        pagination=pagination,
    )


@ticket_bp.route("/ticket/<int:row_number>", methods=["DELETE"])
@admin_required
def delete_ticket(row_number: int):
    db = DatabaseService(current_app.config["DATABASE_PATH"])

    try:
        snapshot = db.get_ticket_snapshot(row_number)
        if not snapshot:
            return jsonify({"ok": False, "error": "Chamado nao encontrado na base local."})

        sheet_row = db.get_sheet_row_for_ticket(row_number)
        service = SheetsService(
            service_account_file=current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
            sheet_id=current_app.config["GOOGLE_SHEETS_ID"],
            sheet_range=current_app.config["GOOGLE_SHEETS_RANGE"],
        )

        deleted_in_sheet = False
        deleted_sheet_row: int | None = None

        if sheet_row:
            service.delete_ticket_row(sheet_row)
            deleted_in_sheet = True
            deleted_sheet_row = sheet_row
        else:
            latest = service.fetch_tickets()
            target_uid = DatabaseService._build_ticket_uid(
                data_hora=snapshot["data_hora"],
                local=snapshot["local"],
                problema=snapshot["problema"],
                solicitante=snapshot["solicitante"],
            )
            for item in latest:
                item_uid = DatabaseService._build_ticket_uid(
                    data_hora=item.data_hora,
                    local=item.local,
                    problema=item.problema,
                    solicitante=item.solicitante,
                )
                if item_uid == target_uid:
                    service.delete_ticket_row(item.row_number)
                    deleted_in_sheet = True
                    deleted_sheet_row = item.row_number
                    break

        if deleted_in_sheet and deleted_sheet_row is not None:
            db.shift_sheet_row_numbers_after_remote_delete(deleted_sheet_row)
            try:
                db.upsert_tickets_from_sheet(service.fetch_tickets())
            except Exception:
                pass

        db.delete_ticket(row_number=row_number)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@ticket_bp.route("/sync/rebuild", methods=["POST"])
@admin_required
def rebuild_from_sheet():
    db = DatabaseService(current_app.config["DATABASE_PATH"])
    service = SheetsService(
        service_account_file=current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
        sheet_id=current_app.config["GOOGLE_SHEETS_ID"],
        sheet_range=current_app.config["GOOGLE_SHEETS_RANGE"],
    )

    try:
        sheet_tickets = service.fetch_tickets()
        db.replace_tickets_from_sheet(sheet_tickets)
        return jsonify({"ok": True, "message": "Base local reconstruida com sucesso."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@ticket_bp.route("/ticket/<int:row_number>/reason", methods=["POST"])
@admin_required
def update_ticket_reason(row_number: int):
    db = DatabaseService(current_app.config["DATABASE_PATH"])
    reason = request.form.get("resolution_reason", "").strip()

    posted_status = request.form.get("current_status", "").strip()
    parsed_posted_status = ""
    if posted_status:
        normalized_status = posted_status.lower()
        if "concl" in normalized_status:
            current_status = "Concluído"
            parsed_posted_status = current_status
        elif "andamento" in normalized_status:
            current_status = "Em andamento"
            parsed_posted_status = current_status
        elif "aberto" in normalized_status:
            current_status = "Em aberto"
        else:
            current_status = db.get_ticket_status(row_number)
    else:
        current_status = db.get_ticket_status(row_number)

    if parsed_posted_status in {"Em andamento", "Concluído"}:
        existing_reason = db.get_ticket_reason(row_number)
        db.set_ticket_status(
            row_number=row_number,
            status=parsed_posted_status,
            resolution_reason=existing_reason,
        )

    updated = db.set_ticket_reason(row_number=row_number, resolution_reason=reason)
    if not updated:
        try:
            service = SheetsService(
                service_account_file=current_app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
                sheet_id=current_app.config["GOOGLE_SHEETS_ID"],
                sheet_range=current_app.config["GOOGLE_SHEETS_RANGE"],
            )
            db.upsert_tickets_from_sheet(service.fetch_tickets())
            updated = db.set_ticket_reason(row_number=row_number, resolution_reason=reason)
        except Exception:
            updated = False

    if not updated:
        return jsonify({"ok": False, "error": "Chamado nao encontrado na base local."})
    return jsonify({"ok": True})


@ticket_bp.route("/login", methods=["GET", "POST"])
def login_page():
    _ensure_bootstrap_admin()
    if _is_authenticated():
        return redirect(url_for("tickets.dashboard"))

    error = None
    username = ""
    next_url = request.args.get("next", "/")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        next_url = request.form.get("next", "/") or "/"

        if _auth_service().authenticate(username, password):
            session["is_admin_authenticated"] = True
            session["admin_username"] = username
            if not next_url.startswith("/"):
                next_url = "/"
            return redirect(next_url)

        error = "Login ou senha invalidos."

    return render_template(
        "login.html",
        error=error,
        username=username,
        next_url=next_url,
    )


@ticket_bp.route("/logout", methods=["POST"])
@admin_required
def logout_page():
    session.pop("is_admin_authenticated", None)
    session.pop("admin_username", None)
    return redirect(url_for("tickets.login_page"))
