from pathlib import Path
from typing import Literal

from pydantic import SecretStr
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


settings = Settings()
