"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the AI Action Agent backend."""

    gcp_project_id: str = "your-gcp-project-id"
    gcp_region: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"

    # Server
    host: str = "0.0.0.0"
    port: int = 4000

    # CORS
    frontend_origin: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
