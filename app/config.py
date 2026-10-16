from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Bassir Leads"
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_MINUTES: int = 720
    DATABASE_URL: str = "sqlite:///./bassir.db"
    ALLOWED_ORIGINS: str = "*"

    ADMIN_EMAIL: str = "admin@bassir.net"
    ADMIN_PASSWORD: str = "ChangeMe123!"
    ADMIN_NAME: str = "Admin"

    DEFAULT_PRICE_SAR: int = 1000
    DAILY_SEND_CAP: int = 50
    SENDER_NAME: str = "Bassir IT"
    DEMO_URL: str = ""

    GOOGLE_PLACES_API_KEY: str = ""
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""  # any secret you choose; Meta sends it back on webhook verification
    WHATSAPP_APP_SECRET: str = ""  # Meta app secret, used to verify X-Hub-Signature-256 on webhooks

    # In-app scheduler: marks overdue invoices, issues monthly invoices on day 1, builds the morning digest
    SCHEDULER_ENABLED: bool = True
    DIGEST_HOUR: int = 8  # Riyadh time (UTC+3)

    # Online payments (Moyasar: Mada, Apple Pay, cards, STC Pay). Empty = bank-transfer instructions on the invoice page.
    MOYASAR_PUBLISHABLE_KEY: str = ""
    MOYASAR_SECRET_KEY: str = ""
    MOYASAR_WEBHOOK_SECRET: str = ""

    # Designer agent (Claude). Leave the key empty to use the built-in sector presets.
    ANTHROPIC_API_KEY: str = ""
    DESIGN_MODEL: str = "claude-opus-5"
    PUBLIC_BASE_URL: str = ""  # e.g. https://leads.bassir.net — used to build proposal links ({proposal})
    UPLOAD_DIR: str = "uploads"


settings = Settings()
