from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "Agent Marketplace"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── AWS Region ───────────────────────────────────────────────────────────
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")

    # ── DynamoDB ─────────────────────────────────────────────────────────────
    dynamodb_table_name: str = Field(
        default="AgentMarketplace", alias="DYNAMODB_TABLE_NAME"
    )

    # ── S3 ───────────────────────────────────────────────────────────────────
    s3_bucket_name: str = Field(default="", alias="S3_BUCKET_NAME")

    # ── AWS Cognito ───────────────────────────────────────────────────────────
    cognito_user_pool_id: str = Field(default="", alias="COGNITO_USER_POOL_ID")
    cognito_client_id: str = Field(default="", alias="COGNITO_CLIENT_ID")
    cognito_region: str = Field(default="us-east-1", alias="COGNITO_REGION")

    # ── AWS Lambda (Agent execution) ──────────────────────────────────────────
    lambda_agent_executor_arn: str = Field(
        default="", alias="LAMBDA_AGENT_EXECUTOR_ARN"
    )

    # ── AWS Secrets Manager (Incremental 2) ──────────────────────────────────
    secrets_manager_region: str = Field(
        default="us-east-1", alias="SECRETS_MANAGER_REGION"
    )

    # ── Anthropic / Claude ───────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # LLM model IDs (from MVP design: Sonnet for planning, Haiku for transforms)
    claude_sonnet_model: str = "claude-sonnet-4-6"
    claude_haiku_model: str = "claude-haiku-4-5-20251001"

    # ── Orchestrator limits (from MVP design §5) ─────────────────────────────
    orchestrator_max_steps: int = 10
    orchestrator_step_timeout_seconds: int = 30

    # ── Agent execution limits (from Incremental 2 §5) ───────────────────────
    agent_max_db_rows: int = 100
    agent_tool_timeout_seconds: int = 30

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"], alias="CORS_ORIGINS"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
