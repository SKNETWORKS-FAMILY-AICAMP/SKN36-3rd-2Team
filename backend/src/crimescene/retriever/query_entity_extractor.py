"""CASE-001 자연어 질문의 엔티티 추출."""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from crimescene.retriever.graph_search import (
    CHARACTER_IDS,
    EVIDENCE_IDS,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState

CASE_ID = "CASE-001"


# 한국어 조사 처리
PARTICLES = (
    "에게",
    "한테",
    "에서",
    "으로",
    "부터",
    "까지",
    "하고",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "와",
    "과",
    "도",
    "만",
    "에",
)

PARTICLE_PATTERN = "|".join(
    re.escape(particle) for particle in sorted(PARTICLES, key=len, reverse=True)
)


@dataclass(frozen=True, slots=True)
class QueryEntityMatch:
    """게임 상태 검증을 통과한 질문 내 엔티티."""

    entity_id: str
    entity_type: str
    start: int


class InaccessibleEntityMentionError(ValueError):
    """접근할 수 없는 엔티티가 질문에 언급된 경우."""


def _find_alias(
    question: str,
    alias: str,
) -> int | None:
    """질문에서 엔티티 이름 또는 ID를 찾는다.

    처리 사항:
        - 한국어 조사 인식
        - 이름 부분 일치 방지
        - 영문 대소문자 무시
        - 등록된 별칭만 인식
    """

    if len(alias) < 2:
        return None

    pattern = (
        rf"(?<![가-힣A-Za-z0-9]){re.escape(alias)}"
        rf"(?=$|[^가-힣A-Za-z0-9]|"
        rf"(?:{PARTICLE_PATTERN})(?=$|[^가-힣A-Za-z0-9]))"
    )

    match = re.search(
        pattern,
        question,
        flags=re.IGNORECASE,
    )

    return match.start() if match else None


def _is_visible(
    entity_id: str,
    state: GameState,
    allowed_entity_ids: set[str],
) -> bool:
    """현재 게임 상태에서 엔티티 검색 가능 여부를 확인한다."""

    # 1. NPC
    if entity_id in CHARACTER_IDS:
        return entity_id in state.unlocked_characters

    # 2. 증거
    if entity_id in EVIDENCE_IDS:
        evidence = state.evidence.get(entity_id)

        return (
            evidence is not None
            and evidence.stage in PolicyEvaluator.VALID_EVIDENCE_STAGES
        )

    # 3. 장소·사건·기타 엔티티
    # 서버가 명시적으로 승인한 ID만 허용
    return entity_id in allowed_entity_ids


def extract_question_entities(
    question: str,
    *,
    registry: Sequence[Mapping[str, object]],
    state: GameState,
    evidence_rules: Mapping[str, EvidenceRule] | None = None,
    allowed_entity_ids: Iterable[str] = (),
    max_entities: int = 10,
    reject_inaccessible_mentions: bool = False,
) -> tuple[QueryEntityMatch, ...]:
    """질문에서 엔티티를 추출하고 GameState로 접근 권한을 확인한다.

    Parameters
    ----------
    question:
        플레이어가 입력한 자연어 질문

    registry:
        서버에서 검증한 엔티티 원본

    state:
        서버가 관리하는 현재 게임 상태

    evidence_rules:
        검증된 증거 규칙

    allowed_entity_ids:
        서버에서 별도로 접근을 승인한 엔티티 ID

    max_entities:
        반환할 최대 엔티티 수

    reject_inaccessible_mentions:
        True이면 접근 불가능한 엔티티가 질문에
        등장했을 때 예외를 발생시킨다.

    Security
    --------
    - 미해금 NPC 검색 차단
    - 미수집 증거 검색 차단
    - 미승인 엔티티 검색 차단
    - 사건 ID 불일치 차단
    - 중복 엔티티 ID 차단
    - 접근 불가능한 엔티티 언급 시 차단 가능

    주의:
        registry와 allowed_entity_ids는 반드시
        신뢰할 수 있는 서버 데이터로 생성해야 한다.
    """

    # --------------------------------------------------
    # 1. 입력값 검증
    # --------------------------------------------------

    if not isinstance(question, str):
        raise TypeError("질문은 문자열이어야 합니다.")

    if not question.strip():
        raise ValueError("질문이 비어 있습니다.")

    if not isinstance(state, GameState):
        raise TypeError("GameState가 필요합니다.")

    if state.case_id != CASE_ID:
        raise ValueError("지원하지 않는 사건 ID입니다.")

    if (
        isinstance(max_entities, bool)
        or not isinstance(max_entities, int)
        or not 1 <= max_entities <= 100
    ):
        raise ValueError("max_entities는 1~100 사이여야 합니다.")

    if not isinstance(reject_inaccessible_mentions, bool):
        raise TypeError("reject_inaccessible_mentions는 bool이어야 합니다.")

    if isinstance(allowed_entity_ids, (str, bytes)):
        raise TypeError("허용 엔티티 ID 목록 형식이 올바르지 않습니다.")

    allowed = set(allowed_entity_ids)

    if any(not isinstance(item, str) for item in allowed):
        raise TypeError("허용 엔티티 ID 타입이 올바르지 않습니다.")

    # --------------------------------------------------
    # 2. 검증된 엔티티 등록 정보 구성
    # --------------------------------------------------

    # entity_id -> (entity_type, aliases)
    entries: dict[str, tuple[str, set[str]]] = {}

    for entity in registry:
        if not isinstance(entity, Mapping):
            raise TypeError("엔티티 등록 정보가 올바르지 않습니다.")

        entity_id = entity.get("entity_id")
        entity_type = entity.get("type")
        label = entity.get("label")
        case_id = entity.get("case_id")

        values = (
            entity_id,
            entity_type,
            label,
            case_id,
        )

        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("엔티티 필수 정보가 누락됐습니다.")

        # CASE-001 외 다른 사건 데이터 차단
        if case_id != state.case_id:
            raise ValueError("엔티티 사건 ID가 일치하지 않습니다.")

        # 동일 ID 중복 등록 차단
        if entity_id in entries:
            raise ValueError("중복된 엔티티 ID가 존재합니다.")

        # 원본의 실제 유형을 유지
        # 접근 권한은 유형이 아니라 _is_visible에서 검증
        entries[entity_id] = (
            entity_type.strip(),
            {
                label.strip(),
                entity_id,
            },
        )

    # --------------------------------------------------
    # 3. 증거 이름을 별칭으로 등록
    # --------------------------------------------------

    if evidence_rules is not None:
        for evidence_id, rule in evidence_rules.items():
            if evidence_id not in EVIDENCE_IDS:
                raise ValueError("지원하지 않는 증거 ID입니다.")

            if not isinstance(rule, EvidenceRule):
                raise TypeError("검증되지 않은 증거 규칙입니다.")

            if evidence_id in entries:
                entity_type, aliases = entries[evidence_id]

                if entity_type != "Evidence":
                    raise ValueError("증거 엔티티 유형이 일치하지 않습니다.")

            else:
                aliases = set()

            aliases.update(
                {
                    evidence_id,
                    rule.name.strip(),
                }
            )

            entries[evidence_id] = (
                "Evidence",
                aliases,
            )

    # --------------------------------------------------
    # 4. 자연어 엔티티 검색
    # --------------------------------------------------

    matches: dict[str, QueryEntityMatch] = {}

    # 동일 별칭이 여러 엔티티를 가리키는 경우 탐지
    claimed_aliases: dict[str, str] = {}

    for entity_id, (entity_type, aliases) in entries.items():
        # ----------------------------------------------
        # 4-1. 접근 권한 검증
        # ----------------------------------------------

        visible = _is_visible(
            entity_id,
            state,
            allowed,
        )

        if not visible:
            # 엄격한 모드에서는 접근 불가능한
            # 엔티티가 질문에 포함됐는지 확인
            if reject_inaccessible_mentions:
                mentioned = any(
                    _find_alias(question, alias) is not None for alias in aliases
                )

                if mentioned:
                    raise InaccessibleEntityMentionError(
                        "접근할 수 없는 엔티티가 포함된 질문입니다."
                    )

            # 일반 모드에서는 검색 후보에서 제외
            continue

        # ----------------------------------------------
        # 4-2. 엔티티 별칭 매칭
        # ----------------------------------------------

        earliest = None

        for alias in aliases:
            start = _find_alias(
                question,
                alias,
            )

            if start is None:
                continue

            normalized_alias = alias.casefold()

            # 동일 이름이 여러 엔티티를 가리키면 차단
            previous_owner = claimed_aliases.get(normalized_alias)

            if previous_owner is not None and previous_owner != entity_id:
                raise ValueError("질문에 중복된 엔티티 이름이 있습니다.")

            claimed_aliases[normalized_alias] = entity_id

            if earliest is None or start < earliest:
                earliest = start

        # ----------------------------------------------
        # 4-3. 검색 결과 생성
        # ----------------------------------------------

        if earliest is not None:
            matches[entity_id] = QueryEntityMatch(
                entity_id=entity_id,
                entity_type=entity_type,
                start=earliest,
            )

    # --------------------------------------------------
    # 5. 질문에 등장한 순서로 정렬
    # --------------------------------------------------

    ordered = sorted(
        matches.values(),
        key=lambda item: (
            item.start,
            item.entity_id,
        ),
    )

    return tuple(ordered[:max_entities])
