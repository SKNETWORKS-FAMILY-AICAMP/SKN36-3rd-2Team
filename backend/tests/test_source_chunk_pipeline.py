"""Source Loader와 Hybrid Chunking 통합 테스트."""

import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5

import pymupdf
import pytest

from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)
from crimescene.ingest.source_chunk_pipeline import (
    build_player_source_chunks,
)
from crimescene.ingest.source_loader import (
    LoadedSourceDocument,
    load_source_documents,
)
from crimescene.scenario.schemas.document import PlayerDocument

CASE_ID = "CASE-001"
POLICY_ID = "POL-TEST-DOC"


def make_document(
    body: str,
    *,
    doc_id: str = "DOC-TEST-001",
) -> PlayerDocument:
    """테스트용 신뢰 원본 문서 생성."""

    return PlayerDocument(
        doc_id=doc_id,
        case_id=CASE_ID,
        title="테스트 문서",
        body=body,
        family="evidence",
        access_scope="collected_evidence",
        truth_status="documented_in_game",
        source_evidence_ids=["E01"],
        known_by_character_ids=[],
        source_doc_ids=[],
        required_evidence=["E01"],
        required_presentations=[],
        required_flags=[],
        required_ending=None,
        protected_fact_ids=[],
        incident_year=2016,
        incident_years=[2016],
        source_refs=[],
        record_id=f"REC-{doc_id}",
        point_id=str(uuid5(NAMESPACE_URL, f"test:{doc_id}")),
        policy_id=POLICY_ID,
        state_version="7.1",
        content_version="1.0",
        build_id="integration-test",
        content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        search_text=body,
    )


def build_records(
    loaded_sources,
    documents,
    *,
    config=None,
):
    """로딩 결과와 신뢰 문서를 연결해 청크 생성."""

    if config is None:
        config = ChunkingConfig()

    bindings = list(
        zip(
            loaded_sources,
            documents,
            strict=True,
        )
    )

    return build_player_source_chunks(
        bindings,
        expected_case_id=CASE_ID,
        valid_policy_ids={POLICY_ID},
        config=config,
    )


def assert_single_chunk(record, document):
    """청크 본문과 핵심 메타데이터 검증."""

    assert record.chunk.source_id == document.doc_id
    assert record.chunk.source_type == "player_document"

    assert record.chunk.case_id == CASE_ID
    assert record.chunk.policy_id == POLICY_ID

    assert record.chunk.body == document.body
    assert record.chunk.search_text == document.search_text

    assert record.chunk.content_hash == document.content_hash

    assert record.chunk.chunk_id == UUID(document.point_id)
    assert record.parent_point_id == UUID(document.point_id)

    assert record.chunk_index == 0
    assert record.chunk_count == 1


def test_markdown_to_hybrid_chunk(tmp_path):
    """Markdown 파일에서 Hybrid 청크 생성."""

    path = tmp_path / "evidence.md"

    path.write_text(
        "# 사건 기록\n\n테스트용 증거 문서입니다.",
        encoding="utf-8",
    )

    loaded = load_source_documents(
        path,
        approved_root=tmp_path,
    )

    document = make_document(loaded[0].body)

    records = build_records(
        loaded,
        [document],
    )

    assert len(records) == 1
    assert_single_chunk(records[0], document)


def test_json_to_hybrid_chunk(tmp_path):
    """JSON 문서에서 Hybrid 청크 생성."""

    path = tmp_path / "record.json"

    path.write_text(
        json.dumps(
            {"body": "테스트용 JSON 사건 기록"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = load_source_documents(
        path,
        approved_root=tmp_path,
    )

    document = make_document(loaded[0].body)

    records = build_records(
        loaded,
        [document],
    )

    assert len(records) == 1
    assert_single_chunk(records[0], document)


def test_jsonl_to_multiple_hybrid_chunks(tmp_path):
    """JSONL의 여러 문서를 각각 청킹한다."""

    path = tmp_path / "records.jsonl"

    rows = [
        {"body": "첫 번째 증거 기록"},
        {"body": "두 번째 증거 기록"},
    ]

    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )

    loaded = load_source_documents(
        path,
        approved_root=tmp_path,
    )

    documents = [
        make_document(
            source.body,
            doc_id=f"DOC-TEST-{index:03d}",
        )
        for index, source in enumerate(
            loaded,
            start=1,
        )
    ]

    records = build_records(
        loaded,
        documents,
    )

    assert len(records) == 2

    assert len({record.chunk.chunk_id for record in records}) == 2

    for record, document in zip(
        records,
        documents,
        strict=True,
    ):
        assert_single_chunk(record, document)


def test_pdf_to_hybrid_chunk(tmp_path):
    """PDF 텍스트 추출 후 Hybrid 청크 생성."""

    path = tmp_path / "report.pdf"

    with pymupdf.open() as pdf:
        page = pdf.new_page()

        page.insert_text(
            (72, 72),
            "Evidence Report",
        )

        pdf.save(path)

    loaded = load_source_documents(
        path,
        approved_root=tmp_path,
    )

    assert len(loaded) == 1
    assert loaded[0].source_format == "pdf"
    assert "Evidence Report" in loaded[0].body

    document = make_document(loaded[0].body)

    records = build_records(
        loaded,
        [document],
    )

    assert len(records) == 1
    assert_single_chunk(records[0], document)


def test_long_markdown_to_fixed_chunks(tmp_path):
    """긴 Markdown 문서를 Fixed-size로 분할한다."""

    path = tmp_path / "long_record.md"

    long_body = "".join(f"{index:04d}" for index in range(460))

    path.write_text(
        long_body,
        encoding="utf-8",
    )

    loaded = load_source_documents(
        path,
        approved_root=tmp_path,
    )

    document = make_document(loaded[0].body)

    config = ChunkingConfig(
        mode=ChunkingMode.FIXED,
    )

    records = build_records(
        loaded,
        [document],
        config=config,
    )

    # 긴 문서는 여러 청크로 분할
    assert len(records) > 1

    # 모든 청크가 같은 원본을 참조
    assert all(record.parent_point_id == UUID(document.point_id) for record in records)

    # 원본 정책 유지
    assert all(record.chunk.policy_id == POLICY_ID for record in records)

    # 청크 길이 제한 준수
    assert all(len(record.chunk.body) <= config.max_chunk_chars for record in records)

    # 청크 순서 및 개수 검증
    assert [record.chunk_index for record in records] == list(range(len(records)))

    assert all(record.chunk_count == len(records) for record in records)

    # 청크 UUID 중복 방지
    assert len({record.chunk.chunk_id for record in records}) == len(records)


def make_loaded_source(
    body: str,
    *,
    source_name: str = "test.md",
    record_number: int | None = None,
) -> LoadedSourceDocument:
    """무결성 검증용 로딩 문서 생성."""

    return LoadedSourceDocument(
        source_name=source_name,
        source_format="markdown",
        body=body,
        record_number=record_number,
    )


def test_source_body_mismatch_rejected(tmp_path):
    """파일 본문과 등록된 원본 문서가 다르면 거부한다."""

    path = tmp_path / "evidence.md"

    path.write_text(
        "실제 파일에 기록된 내용",
        encoding="utf-8",
    )

    loaded = load_source_documents(
        path,
        approved_root=tmp_path,
    )

    document = make_document("서버에 등록된 다른 내용")

    with pytest.raises(
        ValueError,
        match="본문이 일치하지 않습니다",
    ):
        build_records(
            loaded,
            [document],
        )


def test_unknown_policy_rejected():
    """등록되지 않은 접근 정책은 거부한다."""

    body = "테스트 증거 내용"

    source = make_loaded_source(body)
    document = make_document(body)

    with pytest.raises(
        ValueError,
        match="등록되지 않은 접근 정책",
    ):
        build_player_source_chunks(
            [(source, document)],
            expected_case_id=CASE_ID,
            valid_policy_ids={"POL-OTHER"},
            config=ChunkingConfig(),
        )


def test_other_case_rejected():
    """다른 사건의 문서는 등록할 수 없다."""

    body = "다른 사건의 문서"

    source = make_loaded_source(body)

    document = make_document(body).model_copy(update={"case_id": "CASE-999"})

    with pytest.raises(
        ValueError,
        match="다른 사건의 문서",
    ):
        build_records(
            [source],
            [document],
        )


def test_duplicate_source_rejected():
    """동일한 원본 파일 레코드의 중복 등록을 차단한다."""

    body = "동일한 파일 내용"

    source = make_loaded_source(body)

    first_document = make_document(
        body,
        doc_id="DOC-TEST-001",
    )

    second_document = make_document(
        body,
        doc_id="DOC-TEST-002",
    )

    with pytest.raises(
        ValueError,
        match="중복된 원본 파일 레코드",
    ):
        build_records(
            [source, source],
            [first_document, second_document],
        )


def test_duplicate_document_id_rejected():
    """서로 다른 파일에 같은 문서 ID가 있으면 거부한다."""

    body = "중복 문서 ID 테스트"

    sources = [
        make_loaded_source(
            body,
            source_name="first.md",
        ),
        make_loaded_source(
            body,
            source_name="second.md",
        ),
    ]

    document = make_document(
        body,
        doc_id="DOC-TEST-001",
    )

    with pytest.raises(
        ValueError,
        match="중복된 문서 ID",
    ):
        build_records(
            sources,
            [document, document],
        )


def test_empty_bindings_rejected():
    """문서가 하나도 없으면 청킹을 거부한다."""

    with pytest.raises(
        ValueError,
        match="청킹할 문서가 없습니다",
    ):
        build_player_source_chunks(
            [],
            expected_case_id=CASE_ID,
            valid_policy_ids={POLICY_ID},
            config=ChunkingConfig(),
        )


def test_invalid_loaded_source_type_rejected():
    """잘못된 Source 객체 타입을 거부한다."""

    document = make_document("테스트 내용")

    with pytest.raises(
        TypeError,
        match="LoadedSourceDocument 타입",
    ):
        build_player_source_chunks(
            [("잘못된 객체", document)],
            expected_case_id=CASE_ID,
            valid_policy_ids={POLICY_ID},
            config=ChunkingConfig(),
        )


def test_invalid_player_document_type_rejected():
    """잘못된 PlayerDocument 객체 타입을 거부한다."""

    source = make_loaded_source("테스트 내용")

    with pytest.raises(
        TypeError,
        match="PlayerDocument 타입",
    ):
        build_player_source_chunks(
            [(source, "잘못된 객체")],
            expected_case_id=CASE_ID,
            valid_policy_ids={POLICY_ID},
            config=ChunkingConfig(),
        )
