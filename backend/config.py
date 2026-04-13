import logging
import sys

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_INSECURE_JWT_DEFAULTS = {
    "change_me_in_production",
    "change_me_in_production_use_long_random_string",
    "replace_with_long_random_secret_min_32_chars",
    "secret",
    "",
}


class Settings(BaseSettings):
    # ── IBM WatsonX (primary inference) ─────────────────────────────────────
    watsonx_api_key: str = Field(default="", validation_alias="WATSONX_API_KEY")
    watsonx_project_id: str = Field(default="", validation_alias="WATSONX_PROJECT_ID")
    watsonx_url: str = Field(
        default="https://us-south.ml.cloud.ibm.com",
        validation_alias="WATSONX_URL",
    )
    watsonx_model_id: str = Field(
        default="ibm/granite-13b-chat-v2",
        validation_alias="WATSONX_MODEL_ID",
    )

    # ── Infrastructure ────────────────────────────────────────────────────────
    # No hardcoded passwords — must be set via environment / .env
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/citypulse",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")

    # ── Kafka ─────────────────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", validation_alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_enabled: bool = Field(default=True, validation_alias="KAFKA_ENABLED")

    # ── JWT auth ──────────────────────────────────────────────────────────────
    # No default — must be explicitly set; fail fast if missing in production
    jwt_secret: str = Field(
        default="change_me_in_production",
        validation_alias="JWT_SECRET",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60, validation_alias="JWT_EXPIRE_MINUTES")
    jwt_refresh_expire_days: int = Field(default=7, validation_alias="JWT_REFRESH_EXPIRE_DAYS")

    # ── Optional Reddit (social ingestion) ────────────────────────────────────
    reddit_client_id: str = Field(default="", validation_alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", validation_alias="REDDIT_CLIENT_SECRET")

    # ── Runtime ───────────────────────────────────────────────────────────────
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    update_interval_seconds: int = 30
    simulation_batch_size: int = 50

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _security_checks(self) -> "Settings":
        """Fail fast on insecure or missing critical secrets."""
        is_prod = self.environment.lower() == "production"

        # JWT secret must be set and non-trivial in production
        if is_prod and self.jwt_secret in _INSECURE_JWT_DEFAULTS:
            logger.critical(
                "STARTUP ABORTED: JWT_SECRET is not set or uses an insecure default. "
                "Set a strong secret (min 32 random chars) in your environment."
            )
            sys.exit(1)

        # JWT secret minimum length
        if self.jwt_secret not in _INSECURE_JWT_DEFAULTS and len(self.jwt_secret) < 32:
            logger.warning(
                "JWT_SECRET is shorter than 32 characters. "
                "Use a longer random value for security."
            )

        # Warn (don't exit) in development if WatsonX key is absent
        if not self.watsonx_api_key:
            logger.warning(
                "WATSONX_API_KEY is not set — AI scoring will use mock fallback. "
                "Set it in .env to enable real WatsonX inference."
            )

        # In production, WatsonX key is required
        if is_prod and not self.watsonx_api_key:
            logger.critical(
                "STARTUP ABORTED: WATSONX_API_KEY must be set in production."
            )
            sys.exit(1)

        return self

    def log_startup_summary(self) -> None:
        """Log a masked config summary at startup — never logs full key values."""
        def mask(val: str) -> str:
            if not val or val in _INSECURE_JWT_DEFAULTS:
                return "[NOT SET]"
            return val[:4] + "****" + val[-2:] if len(val) > 8 else "****"

        logger.info("── DevCity Pulse startup config ──────────────────────────")
        logger.info("  ENVIRONMENT       : %s", self.environment)
        logger.info("  WATSONX_API_KEY   : %s", mask(self.watsonx_api_key))
        logger.info("  WATSONX_PROJECT_ID: %s", mask(self.watsonx_project_id))
        logger.info("  WATSONX_URL       : %s", self.watsonx_url)
        logger.info("  WATSONX_MODEL_ID  : %s", self.watsonx_model_id)
        logger.info("  JWT_SECRET        : %s", mask(self.jwt_secret))
        logger.info("  DATABASE_URL      : %s", _mask_db_url(self.database_url))
        logger.info("  REDIS_URL         : %s", self.redis_url)
        logger.info("  KAFKA_ENABLED     : %s", self.kafka_enabled)
        logger.info("  REDDIT_CLIENT_ID  : %s", mask(self.reddit_client_id))
        logger.info("──────────────────────────────────────────────────────────")


def _mask_db_url(url: str) -> str:
    """Replace the password portion of a DB URL with ****."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username}:****@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(masked)
    except Exception:
        pass
    return url


settings = Settings()
