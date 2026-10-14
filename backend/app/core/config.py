from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str = ""
    mongodb_db: str = "curriculummind"
    neo4j_uri: str = ""
    neo4j_username: str = ""
    neo4j_password: str = ""
    # DEV ONLY: accept self-signed certs (e.g. antivirus/proxy TLS interception). Never enable in production.
    neo4j_trust_self_signed: bool = False
    # "auto" uses Bolt (port 7687) when it is reachable and falls back to HTTPS (port 443, which networks rarely block);
    # "bolt" / "http" force one. NEO4J_DATABASE is only needed if the database isn't the instance default.
    neo4j_transport: str = "auto"
    neo4j_database: str = ""
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"
    youtube_api_key: str = ""
    jwt_secret: str = ""
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:5173"
    max_upload_mb: int = 20

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
