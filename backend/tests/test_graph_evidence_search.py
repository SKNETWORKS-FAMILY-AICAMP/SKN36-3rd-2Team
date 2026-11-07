"""Neo4j 증거 관계 검색 테스트."""

from unittest.mock import MagicMock

import pytest

from crimescene.retriever.graph_evidence_search import (
    search_character_evidence,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import EvidenceState, GameState


def make_state(*, unlocked=None, evidence=None):
    return GameState(
        case_id="CASE-001",
        session_id="TEST",
        unlocked_characters=(["C01"] if unlocked is None else unlocked),
        evidence={} if evidence is None else evidence,
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def make_rules(holder="C01"):
    return {
        "E01": EvidenceRule(
            name="테스트 증거",
            score=1,
            holder=holder,
            prerequisites=[],
            presentation=[],
            q=[],
        )
    }


def make_driver(rows):
    driver = MagicMock()

    session = driver.session.return_value.__enter__.return_value

    session.run.return_value.data.return_value = rows

    return driver


def test_collected_evidence_visible():
    """수집한 증거는 검색된다."""

    driver = make_driver([{"evidence_id": "E01", "holder_id": "C01"}])

    state = make_state(evidence={"E01": EvidenceState(stage="found")})

    results = search_character_evidence(
        driver,
        "C01",
        state,
        make_rules(),
    )

    assert len(results) == 1
    assert results[0].evidence_id == "E01"


def test_uncollected_evidence_hidden():
    """미수집 증거는 검색되지 않는다."""

    driver = make_driver([])

    results = search_character_evidence(
        driver,
        "C01",
        make_state(),
        make_rules(),
    )

    assert results == []

    driver.session.assert_not_called()


def test_locked_character():
    """미해금 NPC는 검색할 수 없다."""

    driver = make_driver([])

    results = search_character_evidence(
        driver,
        "C01",
        make_state(unlocked=[]),
        make_rules(),
    )

    assert results == []

    driver.session.assert_not_called()


def test_wrong_holder():
    """다른 인물의 증거는 검색하지 않는다."""

    driver = make_driver([])

    state = make_state(evidence={"E01": EvidenceState(stage="found")})

    results = search_character_evidence(
        driver,
        "C01",
        state,
        make_rules(holder="C02"),
    )

    assert results == []


def test_untrusted_evidence_blocked():
    """Neo4j에서 잘못된 증거 ID가 반환되면 차단한다."""

    driver = make_driver([{"evidence_id": "E99", "holder_id": "C01"}])

    state = make_state(evidence={"E01": EvidenceState(stage="found")})

    with pytest.raises(ValueError, match="승인되지 않은"):
        search_character_evidence(
            driver,
            "C01",
            state,
            make_rules(),
        )


def test_untrusted_holder_blocked():
    """Neo4j 보유자 정보가 다르면 차단한다."""

    driver = make_driver([{"evidence_id": "E01", "holder_id": "C02"}])

    state = make_state(evidence={"E01": EvidenceState(stage="found")})

    with pytest.raises(ValueError, match="보유자 정보"):
        search_character_evidence(
            driver,
            "C01",
            state,
            make_rules(),
        )
