"""
Configuration management for Limitless to Memory Box Sync Agent.

Provides centralized configuration with validation and environment variable support.
"""

import os
from typing import Optional
from pydantic import BaseSettings, validator, Field


class Config(BaseSettings):
    """Configuration settings with validation."""
    
    # API Configuration
    limitless_api_key: str = Field(..., description="Limitless API key")
    limitless_api_url: str = Field(
        default="https://api.limitless.ai",
        description="Limitless API base URL"
    )
    
    memorybox_api_key: str = Field(..., description="Memory Box API key/token")
    memorybox_api_url: str = Field(
        default="https://memorybox.amotivv.ai",
        description="Memory Box API base URL"
    )
    memorybox_bucket: str = Field(
        default="Limitless-Lifelogs",
        description="Memory Box bucket name for lifelogs"
    )
    
    # Email Configuration
    mailgun_api_key: str = Field(..., description="Mailgun API key")
    mailgun_domain: str = Field(..., description="Mailgun domain")
    alert_email: str = Field(..., description="Email address for alerts")
    
    # Sync Configuration
    sync_interval_minutes: int = Field(
        default=30,
        description="Sync interval in minutes",
        ge=5,
        le=1440
    )
    batch_size: int = Field(
        default=10,
        description="Number of lifelogs to process per batch",
        ge=1,
        le=100
    )
    timezone: str = Field(
        default="America/Los_Angeles",
        description="Timezone for lifelog processing"
    )
    
    # Performance Configuration
    max_poll_attempts: int = Field(
        default=10,
        description="Maximum attempts to poll Memory Box processing status",
        ge=1,
        le=50
    )
    poll_interval_seconds: int = Field(
        default=2,
        description="Interval between status polling attempts",
        ge=1,
        le=30
    )
    rate_limit_requests_per_minute: int = Field(
        default=180,
        description="Rate limit for Limitless API requests per minute",
        ge=1,
        le=300
    )
    
    # Storage Configuration
    database_path: str = Field(
        default="/app/data/limitless_sync.db",
        description="Path to SQLite database file"
    )
    log_path: str = Field(
        default="/app/logs/",
        description="Directory for log files"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    # Health Check Configuration
    health_check_port: int = Field(
        default=8080,
        description="Port for health check endpoint",
        ge=1024,
        le=65535
    )
    
    @validator('sync_interval_minutes')
    def validate_sync_interval(cls, v):
        """Validate sync interval is reasonable."""
        if v < 5:
            raise ValueError('Sync interval must be at least 5 minutes')
        if v > 1440:
            raise ValueError('Sync interval must be at most 24 hours (1440 minutes)')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level is valid."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {", ".join(valid_levels)}')
        return v.upper()
    
    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone string."""
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(v)
        except Exception:
            # Fallback for older Python versions
            try:
                import pytz
                pytz.timezone(v)
            except Exception:
                raise ValueError(f'Invalid timezone: {v}')
        return v
    
    class Config:
        env_file = '.env'
        case_sensitive = False
        env_prefix = ''
        
        # Field aliases for environment variables
        fields = {
            'limitless_api_key': {'env': 'LIMITLESS_API_KEY'},
            'limitless_api_url': {'env': 'LIMITLESS_API_URL'},
            'memorybox_api_key': {'env': 'MEMORYBOX_API_KEY'},
            'memorybox_api_url': {'env': 'MEMORYBOX_API_URL'},
            'memorybox_bucket': {'env': 'MEMORYBOX_BUCKET'},
            'mailgun_api_key': {'env': 'MAILGUN_API_KEY'},
            'mailgun_domain': {'env': 'MAILGUN_DOMAIN'},
            'alert_email': {'env': 'ALERT_EMAIL'},
            'sync_interval_minutes': {'env': 'SYNC_INTERVAL_MINUTES'},
            'batch_size': {'env': 'BATCH_SIZE'},
            'timezone': {'env': 'TIMEZONE'},
            'max_poll_attempts': {'env': 'MAX_POLL_ATTEMPTS'},
            'poll_interval_seconds': {'env': 'POLL_INTERVAL_SECONDS'},
            'rate_limit_requests_per_minute': {'env': 'RATE_LIMIT_REQUESTS_PER_MINUTE'},
            'database_path': {'env': 'DATABASE_PATH'},
            'log_path': {'env': 'LOG_PATH'},
            'log_level': {'env': 'LOG_LEVEL'},
            'health_check_port': {'env': 'HEALTH_CHECK_PORT'},
        }


def load_config() -> Config:
    """Load and validate configuration from environment variables."""
    try:
        config = Config()
        return config
    except Exception as e:
        print(f"Configuration error: {e}")
        print("Please check your environment variables and .env file")
        raise


def validate_required_config(config: Config) -> None:
    """Validate that all required configuration is present."""
    required_fields = [
        'limitless_api_key',
        'memorybox_api_key', 
        'mailgun_api_key',
        'mailgun_domain',
        'alert_email'
    ]
    
    missing_fields = []
    for field in required_fields:
        value = getattr(config, field, None)
        if not value or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field.upper())
    
    if missing_fields:
        raise ValueError(
            f"Missing required configuration: {', '.join(missing_fields)}. "
            "Please set these environment variables."
        )


def create_directories(config: Config) -> None:
    """Create necessary directories for the application."""
    import pathlib
    
    # Create database directory
    db_dir = pathlib.Path(config.database_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    
    # Create log directory
    log_dir = pathlib.Path(config.log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
