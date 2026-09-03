from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Cohere
    cohere_api_key: str = ""
    cohere_chat_model: str = "command-a-03-2025"
    cohere_embed_model: str = "embed-v4.0"
    cohere_embed_dim: int = 1536
    cohere_rerank_model: str = "rerank-v3.5"

    # Cohere via AWS. "cohere" (default) calls api.cohere.com directly with
    # cohere_api_key above. "bedrock" and "sagemaker" instead call Cohere's own
    # AwsClientV2 subclasses (BedrockClientV2 / SagemakerClientV2, shipped in the
    # same `cohere` SDK we already depend on) using standard AWS credential
    # resolution (env vars, an AWS CLI profile, or an instance/task role) instead
    # of an API key. Model ids on Bedrock/SageMaker are provider-specific, not
    # the same strings as cohere_chat_model above; set them explicitly.
    cohere_provider: str = "cohere"
    aws_region: str = ""
    cohere_bedrock_chat_model: str = ""
    cohere_bedrock_embed_model: str = ""
    cohere_bedrock_rerank_model: str = ""
    cohere_sagemaker_chat_endpoint: str = ""
    cohere_sagemaker_embed_endpoint: str = ""
    cohere_sagemaker_rerank_endpoint: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://triage:triage@localhost:5432/triage"
    database_url_sync: str = "postgresql+psycopg2://triage:triage@localhost:5432/triage"

    # Observability
    otel_exporter_otlp_endpoint: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Integrations (stubbed)
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_escalation_channel: str = "#support-escalations"
    north_automations_webhook_url: str = ""

    # North MCP server (mcp_server.py). trusted_issuers left empty for local dev, where
    # the SDK decodes X-North-ID-Token without signature verification. Set this to your
    # org's identity provider issuer URL(s) before registering this server with real North.
    north_mcp_trusted_issuers: str = ""
    north_mcp_port: int = 5222

    # App
    app_env: str = "local"
    log_level: str = "INFO"
    retrieval_top_k: int = 25
    rerank_top_n: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
