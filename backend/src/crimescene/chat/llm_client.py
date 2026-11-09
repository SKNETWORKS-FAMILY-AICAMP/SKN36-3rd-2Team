"""NPC LLM 공급자 선택: Ollama(개발용) 또는 OpenAI(서비스용).

RAG 허용 문서와 검증 조건은 이 파일에서 변경하지 않습니다.
대화 내용, 원문, API 키는 로그에 기록하지 않습니다.
"""

import logging
import os
from time import perf_counter
from typing import Any

from ollama import Client

from crimescene.settings import settings

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """사용자에게 노출해도 되는 공급자 실패 메시지와 HTTP 상태 코드."""

    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


def _provider() -> str:
    provider = settings.llm_provider.lower().strip()
    if provider not in {"ollama", "openai"}:
        raise LLMProviderError("지원하지 않는 LLM_PROVIDER 설정입니다.")
    return provider


def _max_tokens() -> int:
    try:
        value = int(os.getenv("CRIMESCENE_LLM_MAX_TOKENS", "1024"))
    except ValueError as exc:
        raise ValueError("CRIMESCENE_LLM_MAX_TOKENS는 정수여야 합니다.") from exc
    if not 256 <= value <= 2048:
        raise ValueError("CRIMESCENE_LLM_MAX_TOKENS는 256~2048 사이여야 합니다.")
    return value


# 출처/원문 일치 여부는 기존 npc_output_guard.py에서 별도로 검사합니다.
# 여기서는 기계적으로 올바른 JSON 구조만 생성하도록 요청합니다.
NPC_QUOTES_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "npc_verified_quotes",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "quotes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_id": {"type": "string"},
                            "quote": {"type": "string"},
                        },
                        "required": ["source_id", "quote"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["quotes"],
            "additionalProperties": False,
        },
    },
}


def _openai_generate(messages: list[dict[str, str]], *, json_mode: bool) -> str:
    key = settings.openai_api_key.get_secret_value().strip()
    if not key:
        raise LLMProviderError("OPENAI_API_KEY가 설정되지 않았습니다.")
    if not settings.openai_model.strip():
        raise LLMProviderError("OPENAI_MODEL이 설정되지 않았습니다.")

    try:
        from openai import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            OpenAI,
            RateLimitError,
        )
    except ImportError as exc:
        raise LLMProviderError(
            "OpenAI SDK가 없습니다. uv add openai를 실행하세요."
        ) from exc

    client = OpenAI(
        api_key=key,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,  # 대화 기록이 두 번 기록될 수 있는 숨은 SDK 재시도 방지
    )
    options: dict[str, Any] = {
        "model": settings.openai_model,
        "messages": messages,
        "reasoning_effort": "none",  # 짧은 NPC 인용문 응답을 위해 추론 시간 최소화
        "max_completion_tokens": _max_tokens(),
        "store": False,
    }
    if json_mode:
        options["response_format"] = NPC_QUOTES_SCHEMA

    start = perf_counter()
    try:
        reply = client.chat.completions.create(**options)
    except APITimeoutError as exc:
        raise LLMProviderError(
            "AI 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
            status_code=504,
        ) from exc
    except APIConnectionError as exc:
        raise LLMProviderError(
            "AI 서비스에 연결할 수 없습니다.", status_code=503
        ) from exc
    except RateLimitError as exc:
        raise LLMProviderError(
            "AI 서비스 요청량 또는 사용 한도에 도달했습니다.", status_code=503
        ) from exc
    except APIError as exc:
        # 공급자 예외 원문은 프론트로 전달하거나 로그에 기록하지 않습니다.
        logger.warning("NPC_OPENAI_ERROR kind=%s", type(exc).__name__)
        raise LLMProviderError(
            "AI 응답 생성에 실패했습니다. 서버 설정을 확인해 주세요.", status_code=502
        ) from exc

    usage = reply.usage
    logger.info(
        "NPC_LLM_TIMING provider=openai model=%s wall_sec=%.2f "
        "prompt_tokens=%s output_tokens=%s",
        settings.openai_model,
        perf_counter() - start,
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )
    if not reply.choices:
        raise LLMProviderError("AI에서 비어 있는 응답을 받았습니다.", status_code=502)
    return reply.choices[0].message.content or ""


def generate_response(
    user_message: str,
    system_prompt: str = "당신은 한국어로 답변하는 AI입니다.",
) -> str:
    """기존 일반 답변 생성 API의 함수 규격 유지."""
    if _provider() == "openai":
        return _openai_generate(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            json_mode=False,
        )

    if not settings.ollama_model:
        raise ValueError("OLLAMA_MODEL 환경변수를 설정해 주세요.")
    client = Client(host=settings.ollama_base_url, timeout=120)
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        think=False,
        keep_alive="15m",
        options={"temperature": 0.2},
    )
    return response.message.content or ""


def generate_npc_json(messages: list[dict[str, str]]) -> str:
    """기존 NPC 출력 검증기와 호환되는 JSON 문자열 반환."""
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError("시스템 메시지와 사용자 메시지가 필요합니다.")
    if any(not isinstance(message, dict) for message in messages):
        raise TypeError("LLM 메시지 항목은 딕셔너리여야 합니다.")
    if [message.get("role") for message in messages] != ["system", "user"]:
        raise ValueError("LLM 메시지 역할이 올바르지 않습니다.")
    if any(
        not isinstance(message.get("content"), str) or not message["content"].strip()
        for message in messages
    ):
        raise ValueError("LLM 메시지 내용이 비어 있거나 잘못됐습니다.")

    if _provider() == "openai":
        return _openai_generate(messages, json_mode=True)

    if not settings.ollama_model:
        raise ValueError("OLLAMA_MODEL 환경변수를 설정해 주세요.")

    client = Client(host=settings.ollama_base_url, timeout=120)
    start = perf_counter()
    response = client.chat(
        model=settings.ollama_model,
        messages=messages,
        think=False,
        format="json",
        keep_alive="15m",
        options={"temperature": 0.1, "num_predict": _max_tokens()},
    )
    logger.info(
        "NPC_LLM_TIMING provider=ollama model=%s wall_sec=%.2f "
        "load_sec=%.2f prompt_tokens=%s output_tokens=%s eval_sec=%.2f",
        settings.ollama_model,
        perf_counter() - start,
        (response.load_duration or 0) / 1_000_000_000,
        response.prompt_eval_count,
        response.eval_count,
        (response.eval_duration or 0) / 1_000_000_000,
    )
    return response.message.content or ""
