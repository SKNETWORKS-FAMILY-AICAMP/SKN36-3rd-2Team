from uuid import UUID

import pytest
from pydantic import ValidationError

from crimescene.ingest.chunk_models import RAGChunk


def make_payload(
    source_type: str = "player_document",
) -> dict[str, object]:
    """테스트용 RAG 청크 데이터 생성."""

    payload: dict[str, object] = {
        "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
        "source_id": "DOC-001",
        "source_type": source_type,
        "case_id": "CASE-001",
        "policy_id": "POL-CASE001-DOC-E01",
        "family": "evidence",
        "access_scope": "collected_evidence",
        "character_id": None,
        "incident_year": 2016,
        "content_hash": "test-content-hash",
        "search_text": "검색용 테스트 텍스트",
        "body": "플레이어가 열람할 수 있는 테스트 문서",
    }

    if source_type == "npc_knowledge":
        payload.update(
            {
                "source_id": "K-C01-01",
                "policy_id": "POL-K-C01-01",
                "family": "npc_knowledge",
                "access_scope": "character_only",
                "character_id": "C01",
                "body": "NPC 테스트 진술",
            }
        )

    return payload


def test_valid_player_document_chunk():
    """정상 플레이어 문서 청크 생성."""

    chunk = RAGChunk.model_validate(make_payload())

    assert chunk.source_type == "player_document"
    assert chunk.character_id is None
    assert chunk.policy_id == "POL-CASE001-DOC-E01"
    assert isinstance(chunk.chunk_id, UUID)
    assert chunk.point_id == str(chunk.chunk_id)


def test_valid_npc_knowledge_chunk():
    """정상 NPC 지식 청크 생성."""

    chunk = RAGChunk.model_validate(make_payload("npc_knowledge"))

    assert chunk.source_type == "npc_knowledge"
    assert chunk.character_id == "C01"
    assert chunk.access_scope == "character_only"


def test_invalid_chunk_uuid():
    """잘못된 UUID 입력 차단."""

    payload = make_payload()
    payload["chunk_id"] = "invalid-uuid"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_invalid_policy_id():
    """정책 ID 형식 오류 차단."""

    payload = make_payload()
    payload["policy_id"] = "INVALID-POLICY"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_invalid_npc_access_scope():
    """NPC 지식에 플레이어 문서 접근 범위 사용 차단."""

    payload = make_payload("npc_knowledge")
    payload["access_scope"] = "collected_evidence"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_missing_npc_character_id():
    """NPC 식별자 누락 차단."""

    payload = make_payload("npc_knowledge")
    payload["character_id"] = None

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_invalid_player_access_scope():
    """플레이어 문서에 NPC 전용 범위 사용 차단."""

    payload = make_payload()
    payload["access_scope"] = "character_only"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_player_document_with_character_id():
    """플레이어 문서에 NPC 식별자를 지정하는 경우 차단."""

    payload = make_payload()
    payload["character_id"] = "C01"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "protected_fact_ids",
        "source_refs",
        "admin_truth",
        "engine_only",
    ],
)
def test_forbidden_metadata_rejected(forbidden_field: str):
    """관리자 전용 또는 허용되지 않은 메타데이터 차단."""

    payload = make_payload()
    payload[forbidden_field] = "restricted-data"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_invalid_source_type():
    """정의되지 않은 검색 데이터 유형 차단."""

    payload = make_payload()
    payload["source_type"] = "admin_document"

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_empty_source_id():
    """빈 원본 식별자 차단."""

    payload = make_payload()
    payload["source_id"] = ""

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)


def test_chunk_is_immutable():
    """생성된 청크의 필드 수정 차단."""

    chunk = RAGChunk.model_validate(make_payload())

    with pytest.raises(ValidationError):
        chunk.source_id = "MODIFIED-DOC"


def test_missing_required_field():
    """필수 필드가 없는 청크 생성 차단."""

    payload = make_payload()
    del payload["policy_id"]

    with pytest.raises(ValidationError):
        RAGChunk.model_validate(payload)
