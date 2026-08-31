"""Application configuration management."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # GitHub Configuration
    github_token: str
    fork_repo: str
    upstream_repo: str = "apache/superset"
    
    # Devin API Configuration
    devin_api_key: str
    devin_org_id: str = ""  # Organization ID for v3 API
    devin_api_base_url: str = "https://api.devin.ai/v1"
    
    # Polling Configuration
    poll_interval_minutes: int = 5
    max_issues_per_poll: int = 5
    max_concurrent_sessions: int = 3
    max_issues_to_clone: int = 20
    
    # Application Configuration
    database_url: str = "sqlite:///./devin_automation.db"
    log_level: str = "INFO"
    
    # Labels
    label_cloned: str = "cloned"
    label_pending: str = "devin-pending"
    label_working: str = "devin-working"
    label_done: str = "devin-done"
    label_failed: str = "devin-failed"
    upstream_bug_label: str = "#bug"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
