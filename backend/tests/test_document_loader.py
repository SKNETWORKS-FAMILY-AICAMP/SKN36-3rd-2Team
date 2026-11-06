import json
from pathlib import Path

import pytest

from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_document(
    doc_id: str = "CASE001-DOC-TEST",
) -> dict:
    """테스트용 플레이어 문서 데이터를 생성한다."""

    return {
        "doc_id": doc_id,
        "case_id": "CASE-001",
        "title": "테스트 문서",
        "body": "테스트용 사건 기록입니다.",
        "family": "evidence",
        "access_scope": "collected_evidence",
        "truth_status": "documented_in_game",
        "source_evidence_ids": ["E01"],
        "known_by_character_ids": [],
        "source_doc_ids": ["CASE001-DOC-E01"],
        "required_evidence": [],
        "required_presentations": [],
        "required_flags": [],
        "required_ending": None,
        "protected_fact_ids": [],
        "incident_year": 2026,
        "incident_years": [2026],
        "source_refs": [
            {
                "path": "evidence/CASE001-DOC-E01.md",
                "sha256": "test-hash",
                "json_pointer": "/",
                "dereference_for_llm": False,
            }
        ],
        "record_id": doc_id,
        "point_id": "POINT-TEST",
        "policy_id": "POL-TEST",
        "state_version": "1",
        "content_version": "1",
        "build_id": "TEST",
        "content_hash": "TEST",
        "search_text": "테스트 문서",
    }


def write_jsonl(
    path: Path,
    records: list[dict],
    *,
    encoding: str = "utf-8",
) -> None:
    """테스트 데이터를 JSONL 파일로 저장한다."""

    content = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    path.write_text(
        content,
        encoding=encoding,
    )


def test_load_valid_document(tmp_path):
    """정상적인 문서 하나를 읽는다."""

    path = tmp_path / "documents.jsonl"

    write_jsonl(
        path,
        [make_document()],
    )

    documents = load_player_documents(path)

    assert len(documents) == 1
    assert documents[0].doc_id == "CASE001-DOC-TEST"
    assert documents[0].case_id == "CASE-001"


def test_load_multiple_documents(tmp_path):
    """여러 문서를 정상적으로 읽는다."""

    path = tmp_path / "documents.jsonl"

    write_jsonl(
        path,
        [
            make_document("DOC-001"),
            make_document("DOC-002"),
            make_document("DOC-003"),
        ],
    )

    documents = load_player_documents(path)

    assert len(documents) == 3

    assert [doc.doc_id for doc in documents] == [
        "DOC-001",
        "DOC-002",
        "DOC-003",
    ]


def test_skip_blank_lines(tmp_path):
    """JSONL의 빈 줄은 건너뛴다."""

    path = tmp_path / "documents.jsonl"

    document = json.dumps(
        make_document(),
        ensure_ascii=False,
    )

    path.write_text(
        f"\n{document}\n\n",
        encoding="utf-8",
    )

    documents = load_player_documents(path)

    assert len(documents) == 1


def test_utf8_bom_support(tmp_path):
    """UTF-8 BOM이 포함된 파일을 읽는다."""

    path = tmp_path / "documents.jsonl"

    write_jsonl(
        path,
        [make_document()],
        encoding="utf-8-sig",
    )

    documents = load_player_documents(path)

    assert len(documents) == 1


def test_duplicate_document_id(tmp_path):
    """중복된 문서 ID를 차단한다."""

    path = tmp_path / "documents.jsonl"

    write_jsonl(
        path,
        [
            make_document("DOC-001"),
            make_document("DOC-001"),
        ],
    )

    with pytest.raises(
        ValueError,
        match="중복된 문서 ID",
    ):
        load_player_documents(path)


def test_invalid_json(tmp_path):
    """잘못된 JSON 형식을 차단한다."""

    path = tmp_path / "documents.jsonl"

    path.write_text(
        '{"doc_id": "DOC-001", invalid}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="문서 검증 실패",
    ):
        load_player_documents(path)


def test_missing_required_field(tmp_path):
    """필수 필드가 누락되면 오류를 발생시킨다."""

    path = tmp_path / "documents.jsonl"

    document = make_document()
    del document["body"]

    write_jsonl(path, [document])

    with pytest.raises(
        ValueError,
        match="문서 검증 실패",
    ):
        load_player_documents(path)


def test_invalid_access_scope(tmp_path):
    """정의되지 않은 문서 접근 등급을 차단한다."""

    path = tmp_path / "documents.jsonl"

    document = make_document()
    document["access_scope"] = "admin_only"

    write_jsonl(path, [document])

    with pytest.raises(
        ValueError,
        match="문서 검증 실패",
    ):
        load_player_documents(path)


def test_empty_file(tmp_path):
    """완전히 빈 파일은 허용하지 않는다."""

    path = tmp_path / "documents.jsonl"

    path.write_text("", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="플레이어 문서가 비어 있습니다",
    ):
        load_player_documents(path)


def test_blank_lines_only(tmp_path):
    """빈 줄만 존재하는 파일도 차단한다."""

    path = tmp_path / "documents.jsonl"

    path.write_text(
        "\n\n   \n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="플레이어 문서가 비어 있습니다",
    ):
        load_player_documents(path)


def test_real_v71_documents():
    """실제 v7.1 문서 28개를 검증한다."""

    root = PROJECT_ROOT / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/player_documents.jsonl"))

    if not matches:
        pytest.skip("로컬 v7.1 데이터가 없습니다.")

    assert len(matches) == 1

    documents = load_player_documents(matches[0])

    assert len(documents) == 28

    assert len({document.doc_id for document in documents}) == 28

    assert all(document.case_id == "CASE-001" for document in documents)
