from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://chatbot:chatbot@localhost:5432/chatbot"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "customer_records"
    ollama_url: str = "http://localhost:11434"
    ollama_chat_model: str = "mistral"
    ollama_embed_model: str = "nomic-embed-text"
    token_secret: str = ""
    otp_secret: str = ""
    otp_ttl_seconds: int = 300
    otp_resend_seconds: int = 60
    access_token_ttl_seconds: int = 3600
    dev_otp_delivery: bool = False
    dev_otp_file: str = "./work/dev-otp.txt"
    history_limit: int = 20
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

def validate_settings():
    if settings.app_env != "development" and settings.dev_otp_delivery:
        raise RuntimeError("Development OTP delivery cannot run outside development")
    if len(settings.token_secret) < 32 or len(settings.otp_secret) < 32:
        raise RuntimeError("Set TOKEN_SECRET and OTP_SECRET to random values of at least 32 characters")
