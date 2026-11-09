"""Issue #29 - 비공개 CASE-001 정답 원장 로더."""

from pathlib import Path

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.scenario.case_truth import CaseTruth


def load_case001_truth(path: Path) -> CaseTruth:
    """서버 전용 사건 원장을 검증하여 로딩합니다."""

    if not isinstance(path, Path):
        raise TypeError("사건 원장 경로는 Path여야 합니다.")

    if not path.is_file():
        raise FileNotFoundError("비공개 사건 진실 원장이 없습니다.")

    truth = CaseTruth.model_validate_json(path.read_text(encoding="utf-8-sig"))

    if truth.case_id != "CASE-001":
        raise ValueError("사건 ID가 일치하지 않습니다.")

    if truth.access_scope != "ENGINE_ONLY":
        raise PermissionError("서버 전용 사건 원장이 아닙니다.")

    if truth.perpetrator_character_id not in EXPECTED_CHARACTER_IDS:
        raise ValueError("범인 ID가 CASE-001 인물 목록과 일치하지 않습니다.")

    return truth
