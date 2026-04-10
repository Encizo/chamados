from pathlib import Path
import os

from flask import Flask

from .config import Config
from .controllers.ticket_controller import ticket_bp
from .theme import resolve_palette
from .services.database_service import DatabaseService
from .services.sheets_service import SheetsService
from .services.sync_service import SyncService


def create_app() -> Flask:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            content = line.strip()
            if not content or content.startswith("#") or "=" not in content:
                continue
            key, value = content.split("=", maxsplit=1)
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value

    app = Flask(__name__)
    app.config.from_object(Config)

    palette_key, palette = resolve_palette(app.config.get("APP_THEME_PALETTE"))
    app.config["APP_THEME_PALETTE"] = palette_key
    app.config["APP_THEME_VARS"] = palette["vars"]

    db = DatabaseService(app.config["DATABASE_PATH"])
    db.normalize_all_requester_names()
    sheets = SheetsService(
        service_account_file=app.config["GOOGLE_SERVICE_ACCOUNT_FILE"],
        sheet_id=app.config["GOOGLE_SHEETS_ID"],
        sheet_range=app.config["GOOGLE_SHEETS_RANGE"],
    )
    app.extensions["sync_service"] = SyncService(
        db=db,
        sheets=sheets,
        interval_seconds=app.config.get("SYNC_INTERVAL_SECONDS", 20),
    )

    try:
        app.extensions["sync_service"].force_sync()
    except Exception:
        pass

    app.register_blueprint(ticket_bp)
    return app
