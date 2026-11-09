"""Issue #29 - 실제 비공개 원장 기반 범인 지목 검증."""

import json
from pathlib import Path

import pytest

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.accusation import (
    AccusationStatus,
    enter_accusation,
    submit_accusation,
)
from crimescene.scenario.game_progress import create_initial_state
from crimescene.scenario.loaders.case_truth_loader import load_case001_truth
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.loaders.unlock_graph_loader import (
    load_case001_unlock_rules,
)
from crimescene.scenario.schemas.game_state import (
    EvidenceState,
    GamePhase,
)

ROOT = Path(__file__).resolve().parents[2]
LOCAL_ROOT = ROOT / ".local" / "case001_v7_1"


@pytest.fixture(scope="module")
def real_case():
    """비공개 정답을 출력하지 않고 실제 시나리오를 로딩합니다."""

    private_truth = ROOT / "backend/data/scenario/engine_only/case_truth.json"

    if private_truth.is_file():
        truth_files = [private_truth]
    else:
        truth_files = list(LOCAL_ROOT.glob("*/data/case_truth.json"))

    # CI에는 정답 파일이 없으므로 건너뜁니다.
    if not truth_files:
        pytest.skip("비공개 사건 원장이 없어 실제 정답 검증을 수행하지 못했습니다.")

    if len(truth_files) != 1:
        pytest.fail("비공개 사건 원장이 중복되었습니다.")

    graph_files = list(LOCAL_ROOT.glob("*/data/unlock_graph.json"))
    evidence_files = list(LOCAL_ROOT.glob("*/data/evidence_rules.json"))

    if len(graph_files) != 1 or len(evidence_files) != 1:
        pytest.fail("실제 CASE-001 시나리오 파일 구성이 올바르지 않습니다.")

    truth = load_case001_truth(truth_files[0])

    # 기존 #28 로더로 실제 해금 규칙의 유효성을 검증합니다.
    load_case001_unlock_rules(graph_files[0])
    evidence_rules = load_evidence_rules(evidence_files[0])

    graph = json.loads(graph_files[0].read_text(encoding="utf-8-sig"))

    return truth, evidence_rules, graph


def test_real_truth_is_engine_only(real_case):
    truth, evidence_rules, _ = real_case

    if truth.access_scope != "ENGINE_ONLY":
        pytest.fail("사건 원장의 접근 범위가 올바르지 않습니다.")

    if not set(truth.related_evidence_ids).issubset(evidence_rules):
        pytest.fail("사건 원장의 증거 참조가 일치하지 않습니다.")


def test_real_accusation_all_ten_candidates(real_case):
    truth, evidence_rules, _ = real_case

    state = create_initial_state("issue29-real-verdict")

    state = state.model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "unlocked_characters": sorted(EXPECTED_CHARACTER_IDS),
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in evidence_rules
            },
            "score": sum(rule.score for rule in evidence_rules.values()),
        }
    )

    state = enter_accusation(state, evidence_rules)

    correct_count = 0

    # 실제 범인 ID를 하드코딩하지 않습니다.
    for suspect_id in sorted(EXPECTED_CHARACTER_IDS):
        result = submit_accusation(
            state=state,
            suspect_id=suspect_id,
            truth=truth,
            evidence_rules=evidence_rules,
        )

        if suspect_id == truth.perpetrator_character_id:
            correct_count += 1

            if result.status != AccusationStatus.CORRECT:
                pytest.fail("실제 정답 판정에 실패했습니다.")

            if result.state.outcome != "SUCCESS":
                pytest.fail("정답 지목 후 성공 처리에 실패했습니다.")

        else:
            if result.status != AccusationStatus.INCORRECT:
                pytest.fail("오답 판정에 실패했습니다.")

            if result.state.attempts_left != 2:
                pytest.fail("오답 지목 기회 차감에 실패했습니다.")

    if correct_count != 1:
        pytest.fail("유효한 정답이 정확히 하나여야 합니다.")


def test_real_truth_matches_graph_when_declared(real_case):
    truth, _, graph = real_case

    # 해금 그래프에 범인이 명시된 경우에만 교차 검증합니다.
    # 해당 필드가 없다면 검증하지 않은 것으로 표시합니다.
    if "culprit" not in graph:
        pytest.skip("unlock_graph에 독립적인 범인 ID가 없습니다.")

    if graph["culprit"] != truth.perpetrator_character_id:
        pytest.fail("비공개 사건 원장과 해금 그래프의 범인이 다릅니다.")


def test_accusation_state_does_not_expose_truth(real_case):
    truth, evidence_rules, _ = real_case

    state = create_initial_state("issue29-private-state")

    state = state.model_copy(
        update={
            "phase": GamePhase.INVESTIGATION,
            "unlocked_characters": sorted(EXPECTED_CHARACTER_IDS),
            "evidence": {
                evidence_id: EvidenceState(stage="found")
                for evidence_id in evidence_rules
            },
            "score": 21,
        }
    )

    state = enter_accusation(state, evidence_rules)

    result = submit_accusation(
        state=state,
        suspect_id=truth.perpetrator_character_id,
        truth=truth,
        evidence_rules=evidence_rules,
    )

    public_state = result.state.model_dump()

    # 판정 결과는 공개하되, 비공개 원장은 반환하지 않습니다.
    if "perpetrator_character_id" in public_state:
        pytest.fail("게임 상태에 정답 원장 필드가 노출되었습니다.")

    if "motive" in public_state or "crime_method" in public_state:
        pytest.fail("게임 상태에 비공개 사건 정보가 노출되었습니다.")
