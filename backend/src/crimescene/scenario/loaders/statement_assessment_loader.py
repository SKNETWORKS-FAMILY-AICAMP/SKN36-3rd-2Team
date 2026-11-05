from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter

from crimescene.scenario.adapters.statement_assessment_seed import (
    build_statement_assessment_seeds,
)
from crimescene.scenario.schemas.character import CharacterProfile
from crimescene.scenario.statement_assessment import (
    StatementAssessment,
    StatementIntent,
    StatementTruthStatus,
)

_assessment_adapter = TypeAdapter(list[StatementAssessment])


def load_statement_assessments(
    characters: Sequence[CharacterProfile],
    override_path: Path,
    *,
    case_id: str,
) -> list[StatementAssessment]:
    """기본 진술 평가에 관리자 검증 결과를 반영한다."""

    # 1. 기본 평가 데이터 생성
    seeds = build_statement_assessment_seeds(
        characters,
        case_id=case_id,
    )

    assessments = {assessment.assessment_id: assessment for assessment in seeds}

    if len(assessments) != len(seeds):
        raise ValueError("중복된 기본 진술 평가 ID가 존재합니다.")

    # 2. 관리자 판정 데이터 로딩
    content = override_path.read_text(encoding="utf-8-sig")

    overrides = _assessment_adapter.validate_json(content)

    # 3. 중복 평가 ID 검사
    counts = Counter(assessment.assessment_id for assessment in overrides)

    duplicates = [assessment_id for assessment_id, count in counts.items() if count > 1]

    if duplicates:
        raise ValueError(f"중복된 진술 평가 ID: {duplicates}")

    # 4. 관리자 판정 검증
    for override in overrides:
        original = assessments.get(override.assessment_id)

        if original is None:
            raise ValueError(f"존재하지 않는 진술 평가: {override.assessment_id}")

        if override.case_id != case_id:
            raise ValueError("진술 평가의 사건 ID가 다릅니다.")

        if override.npc_id != original.npc_id:
            raise ValueError("진술 평가의 NPC ID가 다릅니다.")

        if override.knowledge_id != original.knowledge_id:
            raise ValueError("진술 평가의 지식 카드 ID가 다릅니다.")

        # 실제 판정이 내려진 경우 근거 필수
        is_classified = (
            override.truth_status != StatementTruthStatus.UNVERIFIED
            or override.statement_intent != StatementIntent.UNKNOWN
        )

        if is_classified:
            if not override.source_refs:
                raise ValueError("확정된 진술 평가에는 출처가 필요합니다.")

            if not override.explanation:
                raise ValueError("확정된 진술 평가에는 설명이 필요합니다.")

        # 검증 완료된 값으로 교체
        assessments[override.assessment_id] = override

    # 기존 순서 유지
    return [assessments[seed.assessment_id] for seed in seeds]
