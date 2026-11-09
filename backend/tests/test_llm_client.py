from unittest.mock import MagicMock

import pytest

from crimescene.chat import llm_client


@pytest.fixture(autouse=True)
def force_ollama_for_legacy_tests(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "llm_provider", "ollama")


# 1. Ollama 호출 및 응답 검증
def test_generate_response(monkeypatch):
    mock_client = MagicMock()

    mock_client.chat.return_value.message.content = "아직 확인되지 않았습니다."

    mock_client_class = MagicMock(return_value=mock_client)

    monkeypatch.setattr(llm_client, "Client", mock_client_class)
    monkeypatch.setattr(llm_client.settings, "ollama_model", "qwen3:8b")

    response = llm_client.generate_response(
        user_message="신기범은 몇 시에 사망했나요?",
        system_prompt="확인된 사실만 답변하세요.",
    )

    assert response == "아직 확인되지 않았습니다."

    mock_client_class.assert_called_once_with(
        host=llm_client.settings.ollama_base_url,
        timeout=120,
    )
    mock_client.chat.assert_called_once_with(
        model="qwen3:8b",
        messages=[
            {
                "role": "system",
                "content": "확인된 사실만 답변하세요.",
            },
            {
                "role": "user",
                "content": "신기범은 몇 시에 사망했나요?",
            },
        ],
        think=False,
        keep_alive="15m",  # 추가
        options={"temperature": 0.2},
    )


# 2. 모델 설정 누락 테스트
def test_missing_model(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "ollama_model", "")

    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
        llm_client.generate_response(user_message="안녕하세요.")


# 3. 빈 응답 처리 테스트
def test_empty_response(monkeypatch):
    mock_client = MagicMock()
    mock_client.chat.return_value.message.content = None

    monkeypatch.setattr(
        llm_client,
        "Client",
        MagicMock(return_value=mock_client),
    )

    monkeypatch.setattr(llm_client.settings, "ollama_model", "qwen3:8b")

    response = llm_client.generate_response(user_message="안녕하세요.")

    assert response == ""
