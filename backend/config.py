import logging
import warnings

from pydantic_settings import BaseSettings

_cfg_logger = logging.getLogger(__name__)

_INSECURE_JWT_DEFAULT = "dev-secret"


class Settings(BaseSettings):
    # WatsonX
    watsonx_api_key: str = ""
    watsonx_project_id: str = ""
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    # Must match a model deployed for your watsonx project (see deployment space).
    watsonx_model_id: str = "ibm/granite-3-8b-instruct"

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "DevCityPulse/1.0"

    # Infrastructure
    database_url: str = "postgresql://postgres:postgres@localhost:5432/devcitypulse"
    redis_url: str = "redis://localhost:6379"

    # Optional
    news_api_key: str = ""
    ticketmaster_api_key: str = ""
    kafka_bootstrap_servers: str = ""
    jwt_secret: str = _INSECURE_JWT_DEFAULT

    # App — keep batches modest so many parallel WatsonX calls do not stall the sim worker
    update_interval_seconds: int = 30
    simulation_batch_size: int = 12

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

if settings.jwt_secret == _INSECURE_JWT_DEFAULT:
    warnings.warn(
        "JWT_SECRET is using the insecure default 'dev-secret'. "
        "Set a strong JWT_SECRET in your .env file before deploying.",
        stacklevel=1,
    )
