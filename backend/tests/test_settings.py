from crimescene.settings import Settings


# 1. 기본 설정값 테스트
def test_default_settings(monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "AI Crime Scene"
    assert settings.app_env == "development"


# 2. 환경변수 적용 테스트
def test_environment_settings(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Crime Scene Test")
    monkeypatch.setenv("APP_ENV", "test")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Crime Scene Test"
    assert settings.app_env == "test"


# 3. .env 파일 로딩 테스트
def test_env_file_loading(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)

    env_file = tmp_path / ".env"

    env_file.write_text(
        "APP_NAME=Crime Scene\nQDRANT_URL=http://localhost:6333\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "Crime Scene"
    assert settings.qdrant_url == "http://localhost:6333"


# 4. 비밀번호 노출 방지 테스트
def test_password_is_hidden():
    settings = Settings(
        _env_file=None,
        neo4j_password="test-password-123",
    )

    assert "test-password-123" not in repr(settings)
    assert settings.neo4j_password.get_secret_value() == "test-password-123"
