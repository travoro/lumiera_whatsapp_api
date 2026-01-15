"""Configuration management using Pydantic settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application Settings
    environment: str = "development"
    port: int = 8000
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    server_url: str = "https://whatsapp-api.lumiera.paris"  # Public URL for this server

    # Twilio WhatsApp
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str
    twilio_webhook_url: str = ""

    # LLM Provider Selection
    llm_provider: str = "openai"  # Options: openai, anthropic

    # OpenAI GPT
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.7

    # Anthropic Claude (Backup)
    anthropic_api_key: str
    anthropic_model: str = "claude-3-opus-20240229"
    anthropic_max_tokens: int = 4096
    anthropic_temperature: float = 0.7

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_db_url: str = ""

    # PlanRadar
    planradar_api_key: str
    planradar_api_url: str = "https://api.planradar.com/v1"
    planradar_account_id: str

    # LangChain
    langchain_api_key: str = ""
    langchain_tracing_v2: bool = False
    langchain_project: str = "lumiera-whatsapp-copilot"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Translation
    default_language: str = "fr"
    supported_languages: str = "fr,en,es,pt,ar,de,it"

    # Language Detection Policy
    auto_update_user_language: bool = True  # Auto-update user profile language on detection
    language_update_min_message_length: int = 10  # Minimum message length to trigger language update
    language_greeting_exceptions: str = "bonjour,hello,hi,hola,ciao,salut,bună,buna"  # Don't update language for these greetings

    # Audio Transcription
    openai_api_key: str
    whisper_model: str = "whisper-1"
    transcription_target_language: str = "fr"

    # Escalation & Human Handoff
    max_escalation_time: int = 24
    admin_notification_webhook: str = ""
    admin_email: str = ""

    # Rate Limiting & Performance
    rate_limit_per_minute: int = 10
    response_timeout: int = 30
    max_concurrent_requests: int = 5

    # Feature Flags & Intent Classification
    enable_fast_path_handlers: bool = True
    intent_confidence_threshold: float = 0.80  # Keyword: 90%+, Haiku: 80%+
    intent_classification_cache_ttl: int = 300  # 5 minutes in seconds

    # Media Storage
    media_storage_bucket: str = "conversations"  # Supabase storage bucket for media files
    max_file_size_mb: int = 10
    allowed_media_types: str = "image/jpeg,image/png,image/gif,audio/ogg,audio/mpeg,audio/mp4"

    # Security
    secret_key: str
    allowed_webhook_ips: str = ""
    verify_webhook_signature: bool = True

    # Redis (Optional)
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout: int = 5
    enable_redis_cache: bool = False

    # Monitoring (Optional)
    sentry_dsn: str = ""
    enable_sentry: bool = False

    # Development
    debug: bool = False
    hot_reload: bool = True
    mock_external_apis: bool = False

    @property
    def supported_languages_list(self) -> List[str]:
        """Get list of supported languages."""
        return [lang.strip() for lang in self.supported_languages.split(",")]

    @property
    def allowed_media_types_list(self) -> List[str]:
        """Get list of allowed media types."""
        return [media.strip() for media in self.allowed_media_types.split(",")]

    @property
    def language_greeting_exceptions_list(self) -> List[str]:
        """Get list of greeting exceptions (lowercase) that don't trigger language updates."""
        return [greeting.strip().lower() for greeting in self.language_greeting_exceptions.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment.lower() == "development"


# Global settings instance
settings = Settings()
