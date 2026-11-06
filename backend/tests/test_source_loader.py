import json
from pathlib import Path

import pymupdf
import pytest

from crimescene.ingest.source_loader import load_source_documents


def load(path: Path, root: Path):
    """테스트용 문서 로더 호출."""

    return load_source_documents(
        path,
        approved_root=root,
    )


def test_markdown_loading(tmp_path):
    """Markdown 본문을 정상 추출한다."""

    path = tmp_path / "evidence.md"
    path.write_text(
        "# 사건 기록\n\n테스트용 증거입니다.",
        encoding="utf-8",
    )

    documents = load(path, tmp_path)

    assert len(documents) == 1
    assert documents[0].source_name == "evidence.md"
    assert documents[0].source_format == "markdown"
    assert "테스트용 증거입니다." in documents[0].body


def test_markdown_extension_loading(tmp_path):
    """.markdown 확장자도 지원한다."""

    path = tmp_path / "interview.markdown"
    path.write_text(
        "# 인터뷰\n\n테스트 진술",
        encoding="utf-8",
    )

    documents = load(path, tmp_path)

    assert len(documents) == 1
    assert documents[0].source_format == "markdown"


def test_json_single_document(tmp_path):
    """단일 JSON 객체를 로딩한다."""

    path = tmp_path / "record.json"
    path.write_text(
        json.dumps(
            {"body": "테스트용 JSON 문서"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    documents = load(path, tmp_path)

    assert len(documents) == 1
    assert documents[0].body == "테스트용 JSON 문서"
    assert documents[0].source_format == "json"
    assert documents[0].record_number == 1


def test_json_document_array(tmp_path):
    """JSON 배열의 문서를 각각 로딩한다."""

    path = tmp_path / "records.json"
    path.write_text(
        json.dumps(
            [
                {"body": "첫 번째 문서"},
                {"body": "두 번째 문서"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    documents = load(path, tmp_path)

    assert len(documents) == 2
    assert [doc.body for doc in documents] == [
        "첫 번째 문서",
        "두 번째 문서",
    ]
    assert [doc.record_number for doc in documents] == [1, 2]


def test_jsonl_multiple_documents(tmp_path):
    """JSONL을 줄 단위로 로딩한다."""

    path = tmp_path / "records.jsonl"
    path.write_text(
        '{"body": "첫 번째 문서"}\n\n{"body": "두 번째 문서"}\n',
        encoding="utf-8",
    )

    documents = load(path, tmp_path)

    assert len(documents) == 2
    assert documents[0].record_number == 1
    assert documents[1].record_number == 3


def test_jsonl_utf8_bom(tmp_path):
    """UTF-8 BOM이 포함된 JSONL을 로딩한다."""

    path = tmp_path / "bom.jsonl"
    path.write_text(
        '\ufeff{"body": "BOM 테스트"}\n',
        encoding="utf-8",
    )

    documents = load(path, tmp_path)

    assert len(documents) == 1
    assert documents[0].body == "BOM 테스트"


def test_pdf_single_page(tmp_path):
    """PDF 한 페이지의 텍스트를 추출한다."""

    path = tmp_path / "evidence.pdf"

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Evidence Report")
        pdf.save(path)

    documents = load(path, tmp_path)

    assert len(documents) == 1
    assert documents[0].source_format == "pdf"
    assert "Evidence Report" in documents[0].body


def test_pdf_multiple_pages(tmp_path):
    """여러 페이지의 PDF 텍스트를 결합한다."""

    path = tmp_path / "interview.pdf"

    with pymupdf.open() as pdf:
        first_page = pdf.new_page()
        first_page.insert_text((72, 72), "First Interview")

        second_page = pdf.new_page()
        second_page.insert_text((72, 72), "Second Interview")

        pdf.save(path)

    documents = load(path, tmp_path)

    assert len(documents) == 1
    assert "First Interview" in documents[0].body
    assert "Second Interview" in documents[0].body


def test_pdf_without_text_rejected(tmp_path):
    """텍스트가 없는 PDF는 거부한다."""

    path = tmp_path / "empty.pdf"

    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(path)

    with pytest.raises(
        ValueError,
        match="본문이 비어",
    ):
        load(path, tmp_path)


def test_empty_file_rejected(tmp_path):
    """빈 파일을 거부한다."""

    path = tmp_path / "empty.md"
    path.write_bytes(b"")

    with pytest.raises(
        ValueError,
        match="빈 파일",
    ):
        load(path, tmp_path)


def test_blank_markdown_rejected(tmp_path):
    """공백만 있는 Markdown을 거부한다."""

    path = tmp_path / "blank.md"
    path.write_text(
        "   \n\n   ",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="본문이 비어",
    ):
        load(path, tmp_path)


def test_unsupported_extension_rejected(tmp_path):
    """지원하지 않는 확장자를 차단한다."""

    path = tmp_path / "unknown.txt"
    path.write_text(
        "테스트 문서",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="지원하지 않는",
    ):
        load(path, tmp_path)


def test_outside_approved_root_rejected(tmp_path):
    """승인된 디렉터리 밖의 파일은 차단한다."""

    approved = tmp_path / "approved"
    approved.mkdir()

    private = tmp_path / "private.md"
    private.write_text(
        "외부 문서",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="외부",
    ):
        load(private, approved)


def test_file_size_limit(tmp_path):
    """파일 크기 제한 초과 시 거부한다."""

    path = tmp_path / "large.md"
    path.write_text(
        "0123456789",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="크기 제한",
    ):
        load_source_documents(
            path,
            approved_root=tmp_path,
            max_bytes=5,
        )


def test_duplicate_json_keys_rejected(tmp_path):
    """JSON의 중복 Key를 차단한다."""

    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"body": "first", "body": "second"}',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="중복 JSON Key",
    ):
        load(path, tmp_path)


def test_invalid_json_rejected(tmp_path):
    """잘못된 JSON 형식을 거부한다."""

    path = tmp_path / "invalid.json"
    path.write_text(
        '{"body": ',
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        load(path, tmp_path)


def test_json_missing_body_rejected(tmp_path):
    """본문이 없는 JSON 문서를 차단한다."""

    path = tmp_path / "missing.json"
    path.write_text(
        '{"title": "제목만 있는 문서"}',
        encoding="utf-8",
    )

    with pytest.raises(
        TypeError,
        match="문서 본문은 문자열",
    ):
        load(path, tmp_path)


def test_empty_json_array_rejected(tmp_path):
    """빈 JSON 배열을 거부한다."""

    path = tmp_path / "empty_array.json"
    path.write_text(
        "[]",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="목록이 비어",
    ):
        load(path, tmp_path)


def test_jsonl_duplicate_keys_rejected(tmp_path):
    """JSONL의 중복 Key도 차단한다."""

    path = tmp_path / "duplicate.jsonl"
    path.write_text(
        '{"body": "first", "body": "second"}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="중복 JSON Key",
    ):
        load(path, tmp_path)


def test_invalid_jsonl_rejected(tmp_path):
    """JSONL의 잘못된 레코드를 거부한다."""

    path = tmp_path / "invalid.jsonl"
    path.write_text(
        '{"body": "정상 문서"}\n{"body": \n',
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        load(path, tmp_path)
