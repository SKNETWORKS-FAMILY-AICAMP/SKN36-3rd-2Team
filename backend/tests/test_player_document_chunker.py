from uuid import UUID

import pytest

from crimescene.ingest.player_document_chunker import (
    build_player_document_chunks,
)
from crimescene.scenario.schemas.document import PlayerDocument

CASE_ID = "CASE-001"
POLICY_ID = "POL-CASE001-DOC-E01"

POINT_ID_1 = "550e8400-e29b-41d4-a716-446655440000"
POINT_ID_2 = "550e8400-e29b-41d4-a716-446655440001"


def make_document(
    doc_id: str = "DOC-001",
    point_id: str = POINT_ID_1,
    policy_id: str = POLICY_ID,
    case_id: str = CASE_ID,
    access_scope: str = "collected_evidence",
) -> PlayerDocument:
    """테스트용 플레이어 문서를 생성한다."""

    return PlayerDocument(
        doc_id=doc_id,
        case_id=case_id,
        title="테스트 문서",
        body="테스트용 사건 기록입니다.",
        family="evidence",
        access_scope=access_scope,
        truth_status="documented_in_game",
        source_evidence_ids=["E01"],
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=["E01"],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=["TEST-PROTECTED-FACT"],
        incident_year=2016,
        incident_years=[2016],
        source_refs=["TEST-ADMIN-SOURCE-REFERENCE"],
        record_id="REC-001",
        point_id=point_id,
        policy_id=policy_id,
        state_version="7.1",
        content_version="1.0",
        build_id="test-build",
        content_hash="test-content-hash",
        search_text="사건 기록 검색용 테스트 텍스트",
    )


def build_chunks(
    documents: list[PlayerDocument],
    *,
    expected_case_id: str = CASE_ID,
    valid_policy_ids: set[str] | None = None,
):
    """테스트에서 사용할 청킹 함수 호출."""

    if valid_policy_ids is None:
        valid_policy_ids = {POLICY_ID}

    return build_player_document_chunks(
        documents,
        expected_case_id=expected_case_id,
        valid_policy_ids=valid_policy_ids,
    )


def test_valid_player_document_chunk():
    """정상 문서가 하나의 청크로 변환되는지 확인."""

    document = make_document()

    chunks = build_chunks([document])

    assert len(chunks) == 1

    chunk = chunks[0]

    assert chunk.source_id == document.doc_id
    assert chunk.source_type == "player_document"
    assert chunk.case_id == CASE_ID
    assert chunk.policy_id == POLICY_ID

    assert chunk.chunk_id == UUID(document.point_id)
    assert chunk.point_id == document.point_id

    assert chunk.search_text == document.search_text
    assert chunk.body == document.body


def test_conditional_document_chunk():
    """조건부 공개 문서도 정상 변환되는지 확인."""

    document = make_document(
        access_scope="conditional_record",
    )

    chunks = build_chunks([document])

    assert len(chunks) == 1
    assert chunks[0].access_scope == "conditional_record"


def test_multiple_documents_chunking():
    """여러 문서가 각각 독립적인 청크로 생성되는지 확인."""

    documents = [
        make_document(
            doc_id="DOC-001",
            point_id=POINT_ID_1,
        ),
        make_document(
            doc_id="DOC-002",
            point_id=POINT_ID_2,
        ),
    ]

    chunks = build_chunks(documents)

    assert len(chunks) == 2

    assert chunks[0].source_id == "DOC-001"
    assert chunks[1].source_id == "DOC-002"

    assert chunks[0].chunk_id != chunks[1].chunk_id


def test_invalid_policy_reference():
    """등록되지 않은 접근 정책을 사용하는 문서 차단."""

    document = make_document(
        policy_id="POL-UNKNOWN",
    )

    with pytest.raises(
        ValueError,
        match="등록되지 않은 접근 정책",
    ):
        build_chunks([document])


def test_case_id_mismatch():
    """다른 사건의 문서가 섞이는 경우 차단."""

    document = make_document(
        case_id="CASE-999",
    )

    with pytest.raises(
        ValueError,
        match="사건 ID 불일치",
    ):
        build_chunks([document])


def test_duplicate_document_id():
    """문서 ID 중복을 차단하는지 확인."""

    documents = [
        make_document(
            doc_id="DOC-001",
            point_id=POINT_ID_1,
        ),
        make_document(
            doc_id="DOC-001",
            point_id=POINT_ID_2,
        ),
    ]

    with pytest.raises(
        ValueError,
        match="중복 문서 ID",
    ):
        build_chunks(documents)


def test_duplicate_point_id():
    """Qdrant Point ID 중복을 차단하는지 확인."""

    documents = [
        make_document(
            doc_id="DOC-001",
            point_id=POINT_ID_1,
        ),
        make_document(
            doc_id="DOC-002",
            point_id=POINT_ID_1,
        ),
    ]

    with pytest.raises(
        ValueError,
        match="중복 Point ID",
    ):
        build_chunks(documents)


def test_empty_documents():
    """빈 문서 목록을 차단하는지 확인."""

    with pytest.raises(
        ValueError,
        match="청킹 대상 플레이어 문서가 없습니다",
    ):
        build_chunks([])


def test_empty_policy_catalog():
    """접근 정책 목록이 비어 있으면 차단."""

    document = make_document()

    with pytest.raises(
        ValueError,
        match="접근 정책 목록이 비어 있습니다",
    ):
        build_chunks(
            [document],
            valid_policy_ids=set(),
        )


@pytest.mark.parametrize(
    "invalid_case_id",
    ["", "   "],
)
def test_invalid_expected_case_id(invalid_case_id: str):
    """사건 ID가 비어 있거나 공백인 경우 차단."""

    document = make_document()

    with pytest.raises(
        ValueError,
        match="유효한 사건 ID",
    ):
        build_chunks(
            [document],
            expected_case_id=invalid_case_id,
        )


def test_invalid_document_type():
    """PlayerDocument가 아닌 입력을 차단."""

    with pytest.raises(
        TypeError,
        match="PlayerDocument 타입만",
    ):
        build_player_document_chunks(
            [{"doc_id": "DOC-001"}],
            expected_case_id=CASE_ID,
            valid_policy_ids={POLICY_ID},
        )


def test_restricted_metadata_not_copied():
    """내부 참조 및 보호 메타데이터가 청크에 복사되지 않는지 확인."""

    document = make_document()

    chunks = build_chunks([document])

    chunk_data = chunks[0].model_dump()

    assert "source_refs" not in chunk_data
    assert "protected_fact_ids" not in chunk_data
    assert "record_id" not in chunk_data

    assert chunk_data["policy_id"] == POLICY_ID
    assert chunk_data["source_id"] == document.doc_id
