"""PDF, Markdown, JSON, JSONL 문서 로딩 모듈."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SourceFormat = Literal[
    "pdf",
    "markdown",
    "json",
    "jsonl",
]

SUPPORTED_FORMATS: dict[str, SourceFormat] = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".jsonl": "jsonl",
}

MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200


@dataclass(frozen=True, slots=True)
class LoadedSourceDocument:
    """원본 파일에서 추출한 문서.

    이 모델에는 접근 권한 정보가 없으므로
    직접 RAG 인덱싱에 사용해서는 안 된다.
    """

    source_name: str
    source_format: SourceFormat
    body: str
    record_number: int | None = None


def _validate_text(
    value: object,
    *,
    source_name: str,
) -> str:
    """추출된 텍스트의 타입과 내용을 검증한다."""

    if not isinstance(value, str):
        raise TypeError(f"문서 본문은 문자열이어야 합니다: {source_name}")

    text = value.strip()

    if not text:
        raise ValueError(f"문서 본문이 비어 있습니다: {source_name}")

    return text


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """중복 JSON Key를 거부한다."""

    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복 JSON Key: {key}")

        result[key] = value

    return result


def _parse_json_record(
    record: object,
    *,
    source_name: str,
    source_format: SourceFormat,
    record_number: int,
) -> LoadedSourceDocument:
    """JSON 객체의 body 필드를 추출한다."""

    if not isinstance(record, dict):
        raise TypeError(f"JSON 문서는 객체여야 합니다: {source_name}")

    body = _validate_text(
        record.get("body"),
        source_name=source_name,
    )

    return LoadedSourceDocument(
        source_name=source_name,
        source_format=source_format,
        body=body,
        record_number=record_number,
    )


def _load_json(
    text: str,
    *,
    source_name: str,
) -> list[LoadedSourceDocument]:
    """JSON 객체 또는 객체 배열을 로딩한다."""

    data = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_json_keys,
    )

    records = data if isinstance(data, list) else [data]

    if not records:
        raise ValueError("JSON 문서 목록이 비어 있습니다.")

    return [
        _parse_json_record(
            record,
            source_name=source_name,
            source_format="json",
            record_number=index,
        )
        for index, record in enumerate(records, start=1)
    ]


def _load_jsonl(
    text: str,
    *,
    source_name: str,
) -> list[LoadedSourceDocument]:
    """JSONL 문서를 줄 단위로 로딩한다."""

    documents: list[LoadedSourceDocument] = []

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        record = json.loads(
            line,
            object_pairs_hook=_reject_duplicate_json_keys,
        )

        documents.append(
            _parse_json_record(
                record,
                source_name=source_name,
                source_format="jsonl",
                record_number=line_number,
            )
        )

    if not documents:
        raise ValueError("JSONL 문서가 비어 있습니다.")

    return documents


def _load_pdf(
    data: bytes,
    *,
    source_name: str,
) -> LoadedSourceDocument:
    """PDF에서 페이지별 텍스트를 추출한다."""

    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF 로딩에는 PyMuPDF가 필요합니다.") from exc

    pages: list[str] = []

    with pymupdf.open(
        stream=data,
        filetype="pdf",
    ) as pdf:
        if pdf.needs_pass:
            raise ValueError("암호화된 PDF는 로딩할 수 없습니다.")

        if pdf.page_count > MAX_PDF_PAGES:
            raise ValueError("PDF 페이지 제한을 초과했습니다.")

        for page in pdf:
            page_text = page.get_text("text").strip()

            if page_text:
                pages.append(page_text)

    body = _validate_text(
        "\n\n".join(pages),
        source_name=source_name,
    )

    return LoadedSourceDocument(
        source_name=source_name,
        source_format="pdf",
        body=body,
    )


def load_source_documents(
    path: Path,
    *,
    approved_root: Path,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> list[LoadedSourceDocument]:
    """승인된 디렉터리의 문서 파일을 로딩한다.

    지원 형식:
    - PDF
    - Markdown
    - JSON
    - JSONL

    주의:
    - 관리자 전용 데이터는 approved_root에 포함하지 않는다.
    - 반환 결과에는 접근 정책이 포함되지 않는다.
    - 반환 결과를 바로 벡터 DB에 저장해서는 안 된다.
    """

    if max_bytes <= 0:
        raise ValueError("max_bytes는 양수여야 합니다.")

    root = Path(approved_root).resolve(strict=True)
    source = Path(path).resolve(strict=True)

    if not root.is_dir():
        raise NotADirectoryError(f"승인 경로가 디렉터리가 아닙니다: {root}")

    # 심볼릭 링크로 경로 밖에 접근하는 경우도 차단
    if not source.is_relative_to(root):
        raise ValueError("승인된 디렉터리 외부의 파일입니다.")

    if not source.is_file():
        raise ValueError("일반 파일만 로딩할 수 있습니다.")

    source_format = SUPPORTED_FORMATS.get(source.suffix.lower())

    if source_format is None:
        raise ValueError(f"지원하지 않는 문서 형식: {source.suffix}")

    file_size = source.stat().st_size

    if file_size == 0:
        raise ValueError("빈 파일은 로딩할 수 없습니다.")

    if file_size > max_bytes:
        raise ValueError("문서 파일 크기 제한을 초과했습니다.")

    data = source.read_bytes()

    source_name = source.relative_to(root).as_posix()

    if source_format == "pdf":
        return [
            _load_pdf(
                data,
                source_name=source_name,
            )
        ]

    text = data.decode("utf-8-sig")

    if source_format == "markdown":
        return [
            LoadedSourceDocument(
                source_name=source_name,
                source_format="markdown",
                body=_validate_text(
                    text,
                    source_name=source_name,
                ),
            )
        ]

    if source_format == "json":
        return _load_json(
            text,
            source_name=source_name,
        )

    return _load_jsonl(
        text,
        source_name=source_name,
    )
