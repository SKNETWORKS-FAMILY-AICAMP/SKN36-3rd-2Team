"""CASE-001 증거 획득 정책: 검증된 NPC 카드의 effects.find만 신뢰합니다.

원본 증거/지식/정책은 로컬에서 읽으며, 이 모듈은 관리자 진상을 저장하지 않습니다.
"""

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.trigger.npc_trigger import NPCTriggerRule

# 사건 설계 원본(v7.1)과 직접 대조한 증거 발견 카드입니다.
# effect.find와 보유자, 선행 증거, 제시 조건을 시작 시 모두 재검증합니다.
REVIEWED_FIND_CARDS: dict[str, str] = {
    "E01": "K-C01-03",
    "E02": "K-C05-03",
    "E03": "K-C06-04",
    "E04": "K-C04-03",
    "E05": "K-C03-03",
    "E06": "K-C04-07",
    "E07": "K-C08-04",
    "E08": "K-C09-04",
    "E09": "K-C03-04",
    "E10": "K-C05-02",
}

# 원본 evidence_rules.json의 q 질문에서 도출한 주제 키워드입니다.
# 임의의 질문으로 증거를 획득시키는 것이 아니라, 적법한 카드가 실제
# 인용되고 GameState.disclosed_cards에 기록되도록 주제 검색을 여는 역할입니다.
REVIEWED_TOPIC_PHRASES: dict[str, tuple[str, ...]] = {
    "E01": ("일정", "수첩", "21시 기록실", "누구를 만나", "H는 무엇"),
    "E02": ("종이", "찢어진 서류", "오른손", "문서 조각", "현장 사진"),
    "E05": ("출입", "카드", "21시 4분", "차량"),
    "E06": ("백업", "클라우드", "녹음기", "녹음", "서버 사본"),
    "E08": ("비상계단", "목격", "그림자", "후면 통로", "가방"),
    "E09": ("커피", "컵", "라떼", "탕비실"),
    "E10": ("사망 추정", "현장 관찰", "안경", "왼팔", "상태"),
}


@dataclass(frozen=True, slots=True)
class EvidenceAcquisitionSetup:
    policy_ids: dict[str, str]
    evaluator: PolicyEvaluator
    triggers: tuple[NPCTriggerRule, ...]


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def build_evidence_acquisition_setup(
    *,
    evidence_rules: Mapping[str, EvidenceRule],
    policies: Mapping[str, AccessPolicy],
    npc_cards: Iterable[Mapping[str, object]],
) -> EvidenceAcquisitionSetup:
    """실제 NPC 카드가 공개된 후에만 수집 가능한 독립 접근 정책을 생성합니다.

    required_topics를 수집 정책에서 제거하는 이유:
    발견 카드가 승인된 대화에서 실제 인용된 사실을 disclosed_cards로
    검증합니다. 질문 주제 자체는 대화 단계의 기존 접근 정책이 검사합니다.
    """
    if set(evidence_rules) != set(REVIEWED_FIND_CARDS):
        raise ValueError("E01~E10 증거 목록이 승인된 원본과 일치하지 않습니다.")

    cards: dict[str, Mapping[str, object]] = {}
    discovered: dict[str, set[str]] = {
        evidence_id: set() for evidence_id in evidence_rules
    }
    for raw in npc_cards:
        if not isinstance(raw, Mapping):
            raise TypeError("NPC 지식 카드는 객체여야 합니다.")
        card_id = raw.get("id")
        if not isinstance(card_id, str) or not card_id:
            raise ValueError("유효하지 않은 NPC 지식 카드 ID입니다.")
        if card_id in cards:
            raise ValueError(f"중복된 NPC 지식 카드: {card_id}")
        cards[card_id] = raw
        effects = raw.get("effects", {})
        if not isinstance(effects, Mapping):
            raise TypeError(f"NPC 카드 효과 형식 오류: {card_id}")
        found = effects.get("find", [])
        if not isinstance(found, list) or any(not isinstance(x, str) for x in found):
            raise ValueError(f"증거 발견 효과 형식 오류: {card_id}")
        for evidence_id in found:
            if evidence_id not in discovered:
                raise ValueError(f"등록되지 않은 증거 발견 효과: {evidence_id}")
            discovered[evidence_id].add(card_id)

    generated_policies: dict[str, AccessPolicy] = {}
    policy_ids: dict[str, str] = {}
    triggers: list[NPCTriggerRule] = []

    for evidence_id, card_id in REVIEWED_FIND_CARDS.items():
        if discovered[evidence_id] != {card_id}:
            raise ValueError(f"증거 발견 카드 매핑 불일치: {evidence_id}")
        rule = evidence_rules[evidence_id]
        if not isinstance(rule, EvidenceRule) or rule.score <= 0:
            raise ValueError(f"증거 규칙 오류: {evidence_id}")
        card = cards[card_id]
        if card.get("case_id") != "CASE-001" or card.get("character_id") != rule.holder:
            raise ValueError(f"증거 보유자 또는 사건 불일치: {evidence_id}")
        source_policy_id = card.get("policy_id")
        if not isinstance(source_policy_id, str):
            raise TypeError(f"원본 정책 ID 오류: {evidence_id}")
        source_policy = policies.get(source_policy_id)
        if source_policy is None:
            raise ValueError(f"원본 접근 정책 누락: {evidence_id}")
        if not isinstance(source_policy, AccessPolicy):
            raise TypeError("Invalid access policy type")
        if source_policy.required_character != rule.holder:
            raise ValueError(f"원본 정책의 증거 보유자 불일치: {evidence_id}")
        if (
            set(source_policy.required_evidence) != set(rule.prerequisites)
            or set(source_policy.required_presentations) != set(rule.presentation)
            or source_policy.required_flags
            or source_policy.required_ending is not None
        ):
            raise ValueError(f"원본 선행 증거/제시 조건 불일치: {evidence_id}")

        # 실제 NPC 지식 카드 자체의 보호 조건과 접근 정책이 같아야 합니다.
        for attr in ("required_evidence", "required_presentations", "required_topics"):
            raw_conditions = card.get(attr)
            if not isinstance(raw_conditions, list) or set(raw_conditions) != set(
                getattr(source_policy, attr)
            ):
                raise ValueError(f"카드와 원본 정책 조건 불일치: {evidence_id}/{attr}")

        synthetic_id = f"POL-CASE001-ACQUIRE-{evidence_id}"
        if synthetic_id in policies:
            raise ValueError(f"획득 정책 ID 충돌: {synthetic_id}")
        generated_policies[synthetic_id] = AccessPolicy(
            required_evidence=list(source_policy.required_evidence),
            required_presentations=list(source_policy.required_presentations),
            required_flags=list(source_policy.required_flags),
            required_ending=source_policy.required_ending,
            required_topics=[],
            required_disclosed_cards=[
                *source_policy.required_disclosed_cards,
                card_id,
            ],
            required_character=rule.holder,
        )
        policy_ids[evidence_id] = synthetic_id

        if source_policy.required_topics:
            phrases = REVIEWED_TOPIC_PHRASES.get(evidence_id)
            if not phrases or len(source_policy.required_topics) != 1:
                raise ValueError(f"검증된 질문 주제 설정 누락: {evidence_id}")
            questions = tuple(_normalize(q) for q in rule.q)
            if not questions or any(
                not any(_normalize(phrase) in question for question in questions)
                for phrase in phrases
            ):
                raise ValueError(f"사건 원본 질문과 키워드 불일치: {evidence_id}")
            triggers.append(
                NPCTriggerRule(
                    trigger_id=f"TRG-CASE001-{evidence_id}",
                    character_id=rule.holder,
                    policy_id=source_policy_id,
                    topic=source_policy.required_topics[0],
                    phrases=phrases,
                    grant_flags=(),
                )
            )
        elif evidence_id in REVIEWED_TOPIC_PHRASES:
            raise ValueError(f"불필요한 질문 주제 설정: {evidence_id}")

    return EvidenceAcquisitionSetup(
        policy_ids=policy_ids,
        evaluator=PolicyEvaluator(generated_policies),
        triggers=tuple(triggers),
    )
