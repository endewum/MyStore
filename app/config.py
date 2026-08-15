"""Application configuration loaded from environment variables / ``.env``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = ".env"


def _config(prefix: str) -> SettingsConfigDict:
    """Build a settings config that reads ``.env`` with the given env prefix."""
    return SettingsConfigDict(
        env_prefix=prefix,
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class BotSettings(BaseSettings):
    """Telegram bot related settings."""

    model_config = _config("BOT_")

    token: SecretStr = Field(..., description="Token issued by @BotFather")
    parse_mode: Literal["HTML", "MarkdownV2"] = "HTML"
    skip_updates: bool = True
    #: Comma separated Telegram user IDs bootstrapped as SUPER_ADMIN on startup.
    admin_ids: str = ""
    admin_username: str = ""

    @property
    def admin_id_list(self) -> list[int]:
        ids: list[int] = []
        for chunk in self.admin_ids.replace(";", ",").split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                ids.append(int(chunk))
        return ids


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = _config("DB_")

    url: str = Field(
        default="mysql+aiomysql://store:store@localhost:3306/telegram_store",
        description="SQLAlchemy async connection URL",
    )
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_recycle: int = 1800

    @field_validator("url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        if value.startswith(("mysql+pymysql://", "mysql://", "sqlite:///")):
            raise ValueError(
                "DB_URL must use an async driver, "
                "e.g. mysql+aiomysql:// or sqlite+aiosqlite://"
            )
        return value


class RedisSettings(BaseSettings):
    """Optional Redis settings.

    Redis is only used when ``REDIS_ENABLED`` is true; it then backs the FSM
    storage so in-progress admin/customer flows survive a restart. Single
    instance deployments work fine with the default in-memory storage.
    """

    model_config = _config("REDIS_")

    enabled: bool = False
    url: str = "redis://localhost:6379/0"


class WebhookSettings(BaseSettings):
    """Webhook settings. When disabled the bot runs in long-polling mode."""

    model_config = _config("WEBHOOK_")

    enabled: bool = False
    base_url: str = ""
    path: str = "/telegram/webhook"
    secret: SecretStr = SecretStr("")
    host: str = "0.0.0.0"
    port: int = 8080

    @property
    def url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.path}"


class StoreSettings(BaseSettings):
    """Storefront behaviour and business rules."""

    model_config = _config("STORE_")

    name: str = "Digital Store"
    currency: str = "USD"
    #: Storefront grid: 3 columns x 9 rows == 27 products per page.
    products_per_page: int = 27
    product_grid_columns: int = 3
    plans_per_page: int = 8
    orders_per_page: int = 5
    notifications_per_page: int = 5
    admin_list_page_size: int = 8
    #: Minutes an unpaid order stays reserved before it may be auto-cancelled.
    payment_timeout_minutes: int = 60
    support_username: str = ""
    #: Broadcast pacing – Telegram allows roughly 30 messages/second overall.
    broadcast_messages_per_second: int = 20
    broadcast_batch_size: int = 25


class SecuritySettings(BaseSettings):
    """Rate limiting / anti-flood settings."""

    model_config = _config("SECURITY_")

    rate_limit_enabled: bool = True
    #: Minimum seconds between two consecutive updates from the same user.
    rate_limit_interval: float = 0.45
    #: Violations tolerated before the user is warned.
    rate_limit_burst: int = 5
    admin_secret: SecretStr = SecretStr("")


class LoggingSettings(BaseSettings):
    model_config = _config("LOG_")

    level: str = "INFO"
    json_format: bool = False


class Settings(BaseSettings):
    """Root settings object aggregating every configuration section."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "staging", "production"] = "development"
    bot: BotSettings = Field(default_factory=BotSettings)  # type: ignore[arg-type]
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)
    store: StoreSettings = Field(default_factory=StoreSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
