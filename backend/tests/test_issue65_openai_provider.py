"""API 네트워크 요청 없이 OpenAI 공급자 분기와 JSON 계약을 검증합니다."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest
from pydantic import SecretStr

from crimescene.chat import llm_client


@pytest.fixture
def openai_mock(monkeypatch):
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"quotes":[]}'))],
        usage=SimpleNamespace(prompt_tokens=900, completion_tokens=45),
    )
    cls = MagicMock(return_value=client)
    monkeypatch.setattr(openai, "OpenAI", cls)
    monkeypatch.setattr(llm_client.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm_client.settings, "openai_model", "gpt-5.6-luna")
    monkeypatch.setattr(
        llm_client.settings, "openai_api_key", SecretStr("test-only-key")
    )
    return cls, client


def test_openai_npc_json_preserves_existing_interface(openai_mock):
    cls, client = openai_mock
    raw = llm_client.generate_npc_json(
        [
            {"role": "system", "content": "JSON 인용만 반환하세요."},
            {"role": "user", "content": "자료를 인용하세요."},
        ]
    )
    assert raw == '{"quotes":[]}'
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5.6-luna"
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["store"] is False
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["max_completion_tokens"] >= 256
    assert cls.call_args.kwargs["max_retries"] == 0


def test_openai_plain_response(openai_mock):
    _, client = openai_mock
    client.chat.completions.create.return_value.choices[
        0
    ].message.content = "확인되지 않았습니다."
    answer = llm_client.generate_response("사망 시각은?", "확인된 사실만 답하세요.")
    assert answer == "확인되지 않았습니다."
    assert "response_format" not in client.chat.completions.create.call_args.kwargs


def test_missing_api_key_rejected_before_network(monkeypatch, openai_mock):
    _, client = openai_mock
    monkeypatch.setattr(llm_client.settings, "openai_api_key", SecretStr(""))
    with pytest.raises(llm_client.LLMProviderError, match="OPENAI_API_KEY"):
        llm_client.generate_npc_json(
            [
                {"role": "system", "content": "JSON을 반환하세요."},
                {"role": "user", "content": "질문입니다."},
            ]
        )
    client.chat.completions.create.assert_not_called()


def test_openai_timeout_returns_safe_error(monkeypatch, openai_mock):
    _, client = openai_mock
    client.chat.completions.create.side_effect = openai.APITimeoutError(
        request=MagicMock()
    )
    with pytest.raises(llm_client.LLMProviderError) as exc:
        llm_client.generate_response("질문")
    assert exc.value.status_code == 504
    assert "test-only-key" not in str(exc.value)


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "llm_provider", "unknown")
    with pytest.raises(llm_client.LLMProviderError, match="LLM_PROVIDER"):
        llm_client.generate_response("질문")
