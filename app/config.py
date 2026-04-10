import os

from dotenv import load_dotenv


load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    APP_BOOTSTRAP_ADMIN_USER = os.getenv("APP_BOOTSTRAP_ADMIN_USER", "admin")
    APP_BOOTSTRAP_ADMIN_PASS = os.getenv("APP_BOOTSTRAP_ADMIN_PASS", "admin123")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME_MINUTES = int(os.getenv("PERMANENT_SESSION_LIFETIME_MINUTES", "720"))
    GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_SHEETS_RANGE = os.getenv("GOOGLE_SHEETS_RANGE", "Respostas ao formulario 1!A:E")
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    APP_BRAND_SHORT = os.getenv("APP_BRAND_SHORT", "SEMSAU")
    APP_BRAND_NAME = os.getenv("APP_BRAND_NAME", "Painel de Chamados")
    APP_ORG_NAME = os.getenv("APP_ORG_NAME", "Secretaria Municipal de Saude")
    APP_TICKETS_TITLE = os.getenv("APP_TICKETS_TITLE", "Painel de Chamados TI - SEMSAU")
    APP_DASHBOARD_TITLE = os.getenv("APP_DASHBOARD_TITLE", "Dashboard SEMSAU IT")
    APP_TICKETS_SUBTITLE = os.getenv(
        "APP_TICKETS_SUBTITLE",
        "Atendimento em tempo real integrado ao Google Forms e Google Sheets.",
    )
    APP_THEME_PALETTE = os.getenv("APP_THEME_PALETTE", "azul-tech")
    APP_LOCAL_COLORS_JSON = os.getenv("APP_LOCAL_COLORS_JSON", "{}")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/chamados.db")
    SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "20"))
