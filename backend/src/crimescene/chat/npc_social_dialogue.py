"""Issue #25 - NPC별 안전한 일상 대화."""

import re
from typing import Literal

SocialIntent = Literal[
    "greeting",
    "talk",
    "thanks",
    "farewell",
]

MAX_SOCIAL_LENGTH = 120

# 사건과 무관한 안전한 일상 표현만 허용
SOCIAL_PATTERNS = {
    "greeting": re.compile(r"(?:안녕하세요|안녕하십니까|안녕)"),
    "talk": re.compile(
        r"(?:(?:안녕하세요|안녕하십니까)[.!]?\s*)?"
        r"(?:잠깐\s*)?"
        r"(?:이야기(?:를)?\s*나눌\s*수\s*있을까요"
        r"|대화(?:를)?\s*할\s*수\s*있을까요"
        r"|이야기\s*좀\s*해도\s*될까요)"
    ),
    "thanks": re.compile(r"(?:감사합니다|고맙습니다|고마워요)"),
    "farewell": re.compile(r"(?:안녕히\s*계세요|다음에\s*뵙겠습니다|이만\s*가볼게요)"),
}

# 순서: 인사 / 대화 요청 / 감사 / 작별
SOCIAL_RESPONSES = {
    "C01": (
        "안녕하세요. 말씀해 보시죠.",
        "네. 잠시라면 괜찮습니다. 무슨 일입니까?",
        "별말씀을요.",
        "조심히 가십시오.",
    ),
    "C02": (
        "안녕하세요.",
        "말씀하세요. 듣겠습니다.",
        "네, 알겠습니다.",
        "안녕히 가세요.",
    ),
    "C03": (
        "아, 안녕하세요.",
        "네, 괜찮습니다. 어떤 이야기인데요?",
        "아닙니다. 별말씀을요.",
        "네, 들어가세요.",
    ),
    "C04": (
        "안녕하세요.",
        "네. 말씀하세요.",
        "괜찮습니다.",
        "안녕히 가십시오.",
    ),
    "C05": (
        "안녕하세요.",
        "네. 편하게 말씀해 주세요. 듣고 있겠습니다.",
        "도움이 됐다면 다행입니다.",
        "조심해서 가세요.",
    ),
    "C06": (
        "안녕하세요. 반갑습니다.",
        "네. 천천히 말씀해 주셔도 됩니다.",
        "아닙니다. 괜찮습니다.",
        "다음에 뵙겠습니다.",
    ),
    "C07": (
        "안녕하세요! 반갑네요.",
        "그럼요. 무슨 이야기부터 할까요?",
        "에이, 별말씀을요.",
        "또 봬요!",
    ),
    "C08": (
        "안녕하세요.",
        "그러시죠. 듣고 있습니다.",
        "뭘요.",
        "안녕히 가세요.",
    ),
    "C09": (
        "안녕하세요. 반갑습니다.",
        "네. 제가 들을 수 있는 이야기라면요.",
        "아닙니다. 별말씀을요.",
        "다음에 또 뵙겠습니다.",
    ),
    "C10": (
        "안녕하세요. 무슨 일이세요?",
        "좋습니다. 어떤 이야기죠?",
        "네, 괜찮습니다.",
        "그럼 다음에 뵙죠.",
    ),
}

INTENT_INDEX = {
    "greeting": 0,
    "talk": 1,
    "thanks": 2,
    "farewell": 3,
}

REPEAT_OPENERS = {
    "C01": "다시 뵙네요.",
    "C02": "또 오셨군요.",
    "C03": "아, 또 오셨네요.",
    "C04": "또 오셨네요.",
    "C05": "다시 뵈니 반갑습니다.",
    "C06": "또 뵙게 됐네요.",
    "C07": "어, 또 오셨네요!",
    "C08": "또 오셨군요.",
    "C09": "다시 뵙게 됐네요.",
    "C10": "또 오셨네요.",
}


def match_safe_social_intent(
    question: str,
) -> SocialIntent | None:
    """안전한 일상 표현과 문장 전체가 일치하는지 확인한다."""

    if not isinstance(question, str):
        raise TypeError("질문은 문자열이어야 합니다.")

    normalized = question.strip().rstrip("?.!~… \t\r\n")

    if not normalized or len(normalized) > MAX_SOCIAL_LENGTH:
        return None

    for intent, pattern in SOCIAL_PATTERNS.items():
        if pattern.fullmatch(normalized):
            return intent

    return None


def build_safe_social_reply(
    character_id: str,
    question: str,
    *,
    repeated: bool = False,
) -> str:
    """서버에 등록된 NPC 응답만 반환한다."""

    if character_id not in SOCIAL_RESPONSES:
        raise ValueError("유효하지 않은 NPC입니다.")

    intent = match_safe_social_intent(question)

    if intent is None:
        raise ValueError("안전한 일상 대화로 분류되지 않았습니다.")

    response = SOCIAL_RESPONSES[character_id][INTENT_INDEX[intent]]

    if repeated and intent in {"greeting", "talk"}:
        return f"{REPEAT_OPENERS[character_id]} {response}"

    return response


def is_approved_social_reply(
    character_id: str,
    question: str,
    answer: str,
) -> bool:
    """저장 전 서버에 등록된 일상 응답인지 재검증한다."""

    if not isinstance(answer, str):
        return False

    if character_id not in SOCIAL_RESPONSES:
        return False

    if match_safe_social_intent(question) is None:
        return False

    return answer in {
        build_safe_social_reply(
            character_id,
            question,
            repeated=False,
        ),
        build_safe_social_reply(
            character_id,
            question,
            repeated=True,
        ),
    }
