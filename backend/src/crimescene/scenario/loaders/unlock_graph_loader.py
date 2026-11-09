"""Issue #28 - CASE-001 실제 게임 해금 규칙 로더."""

import json
from dataclasses import dataclass
from pathlib import Path

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.flag_progress import parse_flag_source
from crimescene.scenario.npc_unlock import NPCUnlockRule
from crimescene.scenario.schemas.evidence import EvidenceRule

EXPECTED_EVIDENCE_IDS = {f"E{i:02d}" for i in range(1, 11)}
EXPECTED_FLAG_IDS = {f"L{i:02d}" for i in range(1, 6)}


@dataclass(frozen=True, slots=True)
class Case001UnlockRules:
    npc_rules: dict[str, NPCUnlockRule]
    flag_requirements: dict[str, frozenset[str]]
    flag_sources: dict[str, str]


def _parse_requirements(
    value: object,
    *,
    valid_ids: set[str],
    field_name: str,
) -> frozenset[str]:
    """규칙 참조가 실제 등록된 ID인지 확인합니다."""

    if not isinstance(value, list):
        raise TypeError(f"{field_name}: 목록이 필요합니다.")

    if any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name}: 문자열 ID가 필요합니다.")

    if not set(value).issubset(valid_ids):
        raise ValueError(f"{field_name}: 존재하지 않는 ID가 있습니다.")

    if len(value) != len(set(value)):
        raise ValueError(f"{field_name}: 중복된 ID가 있습니다.")

    return frozenset(value)


def load_case001_unlock_rules(path: Path) -> Case001UnlockRules:
    """관리자 전용 unlock_graph에서 해금 조건만 추출합니다."""

    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, dict):
        raise TypeError("해금 그래프는 JSON 객체여야 합니다.")

    if data.get("case_id") != "CASE-001":
        raise ValueError("지원하지 않는 사건입니다.")

    characters = data.get("characters")
    evidence = data.get("evidence")
    flags = data.get("flags")

    if not all(isinstance(section, dict) for section in (characters, evidence, flags)):
        raise TypeError("게임 규칙 구조가 올바르지 않습니다.")

    expected_characters = set(EXPECTED_CHARACTER_IDS)

    if set(characters) != expected_characters:
        raise ValueError("NPC 목록이 C01~C10과 일치하지 않습니다.")

    if set(evidence) != EXPECTED_EVIDENCE_IDS:
        raise ValueError("증거 목록이 E01~E10과 일치하지 않습니다.")

    if set(flags) != EXPECTED_FLAG_IDS:
        raise ValueError("진행 플래그 목록이 L01~L05와 일치하지 않습니다.")

    if (
        data.get("start_characters") != ["C01"]
        or data.get("start_evidence") != []
        or data.get("score_threshold") != 11
        or data.get("score_total") != 21
        or data.get("accusation_attempts") != 3
    ):
        raise ValueError("게임 초기 설정이 기존 엔진과 다릅니다.")

    total_score = 0

    for evidence_id, raw_rule in evidence.items():
        rule = EvidenceRule.model_validate(raw_rule)

        if rule.holder not in expected_characters:
            raise ValueError(f"{evidence_id}: 잘못된 증거 보유 NPC입니다.")

        _parse_requirements(
            rule.prerequisites,
            valid_ids=EXPECTED_EVIDENCE_IDS,
            field_name=f"{evidence_id}.prerequisites",
        )

        total_score += rule.score

    if total_score != 21:
        raise ValueError("증거 점수의 합계가 21점이 아닙니다.")

    # 최초 NPC인 C01은 자동 해금 규칙에서 제외합니다.
    npc_rules: dict[str, NPCUnlockRule] = {}

    for npc_id, info in sorted(characters.items()):
        if not isinstance(info, dict):
            raise TypeError(f"{npc_id}: NPC 규칙이 올바르지 않습니다.")

        requirements = _parse_requirements(
            info.get("unlock"),
            valid_ids=EXPECTED_EVIDENCE_IDS,
            field_name=f"{npc_id}.unlock",
        )

        if npc_id == "C01":
            if requirements:
                raise ValueError("최초 NPC에는 해금 조건이 없어야 합니다.")
            continue

        if not requirements:
            raise ValueError(f"{npc_id}: 해금 조건이 비어 있습니다.")

        npc_rules[npc_id] = NPCUnlockRule(
            required_evidence=requirements,
        )
    flag_requirements: dict[str, frozenset[str]] = {}
    flag_sources: dict[str, str] = {}

    for flag_id, info in sorted(flags.items()):
        if not isinstance(info, dict):
            raise TypeError(f"{flag_id}: 플래그 규칙이 올바르지 않습니다.")

        flag_requirements[flag_id] = _parse_requirements(
            info.get("requires"),
            valid_ids=EXPECTED_EVIDENCE_IDS,
            field_name=f"{flag_id}.requires",
        )

        source = info.get("source")

        if not isinstance(source, str):
            raise TypeError(f"{flag_id}: source가 문자열이 아닙니다.")

        # 지원하지 않는 이벤트 표현식은 로딩 단계에서 차단합니다.
        parse_flag_source(source)
        flag_sources[flag_id] = source

    return Case001UnlockRules(
        npc_rules=npc_rules,
        flag_requirements=flag_requirements,
        flag_sources=flag_sources,
    )
