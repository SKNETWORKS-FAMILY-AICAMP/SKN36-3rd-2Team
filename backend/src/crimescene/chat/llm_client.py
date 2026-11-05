from ollama import Client

from crimescene.settings import settings


def generate_response(
    user_message: str,
    system_prompt: str = "당신은 한국어로 답변하는 AI입니다.",
) -> str:
    """
    Ollama를 이용하여 LLM 응답을 생성합니다.

    Args:
        user_message: 사용자 질문
        system_prompt: LLM에 적용할 시스템 프롬프트

    Returns:
        LLM이 생성한 텍스트 응답
    """

    # 모델 설정 확인
    if not settings.ollama_model:
        raise ValueError("OLLAMA_MODEL 환경변수를 설정해 주세요.")

    # Ollama 클라이언트 생성
    client = Client(host=settings.ollama_base_url)

    # LLM 호출
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
        think=False,
        options={
            "temperature": 0.2,
        },
    )

    return response.message.content or ""


if __name__ == "__main__":
    system_prompt = """
    당신은 AI 추리 게임의 사건 조사관입니다.

    [확인된 사건 정보]
    - 피해자 이름: 신기범
    - 사건명: 마지막 기록: 사라진 공동체
    - 사망 시각: 확인되지 않음

    [답변 규칙]
    1. 제공된 사건 정보만 사용하세요.
    2. 확인되지 않은 사실은 만들어내지 마세요.
    3. 정보가 없다면 '아직 확인되지 않았습니다.'라고 답하세요.
    4. 한국어로 간결하게 답변하세요.
    """

    answer = generate_response(
        user_message="신기범은 몇 시에 사망했나요?",
        system_prompt=system_prompt,
    )

    print("LLM 응답:", answer)
