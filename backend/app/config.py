"""
Application configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AliyunDrive OAuth credentials
    aliyun_client_id: str = ""
    aliyun_client_secret: str = ""

    # Encryption key for token storage (Fernet key, base64-encoded 32 bytes)
    encryption_key: str = ""

    # Database URL (SQLite by default)
    database_url: str = "sqlite:///./data/app.db"

    # API rate limiting
    api_call_interval_ms: int = 500  # milliseconds between API calls (increased from 200)
    api_max_retries: int = 5
    api_max_backoff_seconds: int = 60
    
    # API timeout settings
    api_connect_timeout: float = 10.0   # Connection timeout in seconds
    api_read_timeout: float = 30.0      # Read timeout in seconds
    api_write_timeout: float = 30.0     # Write timeout in seconds
    api_pool_timeout: float = 10.0      # Pool timeout in seconds

    # CORS origins allowed
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # AliyunDrive API base URL
    aliyun_api_base_url: str = "https://open.alipan.com"

    # OAuth redirect URI
    oauth_redirect_uri: str = "http://localhost:8000/api/auth/callback"


settings = Settings()
