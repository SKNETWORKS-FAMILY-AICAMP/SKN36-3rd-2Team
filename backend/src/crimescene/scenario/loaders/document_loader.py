from pathlib import Path

from pydantic import ValidationError

from crimescene.scenario.schemas.document import PlayerDocument


def load_player_documents(
    path: Path,
) -> list[PlayerDocument]:
    """JSONL 파일에서 플레이어 문서를 읽고 검증한다.

    검증 항목:
    - JSON 형식
    - Pydantic 스키마
    - 문서 ID 중복
    - 빈 데이터
    """

    documents: list[PlayerDocument] = []
    seen_ids: set[str] = set()

    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as file:
        for line_number, line in enumerate(file, start=1):
            # 빈 줄은 건너뛴다.
            if not line.strip():
                continue

            # 1. JSON 및 Pydantic 검증
            try:
                document = PlayerDocument.model_validate_json(line)
            except ValidationError as exc:
                raise ValueError(f"문서 검증 실패: {path}, line={line_number}") from exc

            # 2. 문서 ID 중복 검사
            if document.doc_id in seen_ids:
                raise ValueError(
                    f"중복된 문서 ID: {document.doc_id} (line={line_number})"
                )

            seen_ids.add(document.doc_id)
            documents.append(document)

    # 3. 빈 파일 검사
    if not documents:
        raise ValueError(f"플레이어 문서가 비어 있습니다: {path}")

    return documents
