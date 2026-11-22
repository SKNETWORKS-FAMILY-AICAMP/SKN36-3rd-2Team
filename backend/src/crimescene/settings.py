from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "AI Crime Scene"
    app_env: str = "development"

    # NPC 응답 생성 공급자. 임베딩은 기존 Ollama bge-m3를 사용합니다.
    llm_provider: Literal["ollama", "openai"] = "ollama"
    openai_model: str = "gpt-5.6-luna"
    openai_api_key: SecretStr = SecretStr("")
    openai_timeout_seconds: float = 35.0

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")

    crimescene_case001_root: Path = Path(".local/case001_v7_1")

    # Django 콘텐츠 서비스
    django_content_base_url: str = "http://127.0.0.1:8001"
    django_content_service_token: SecretStr = SecretStr("")
    django_content_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=30,
    )
    django_content_enabled: bool = False
    django_evidence_gate_enabled: bool = False


settings = Settings()
