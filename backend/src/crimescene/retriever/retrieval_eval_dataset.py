"""CASE-001 검색 품질 평가 데이터셋 로더 및 검증."""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from crimescene.ingest.hybrid_chunker import HybridChunkRecord

QueryType = Literal[
    "keyword",
    "paraphrase",
    "multi_document",
]

SourceType = Literal[
    "player_document",
    "npc_knowledge",
]

REQUIRED_FIELDS = frozenset(
    {
        "question_id",
        "question",
        "query_type",
        "case_id",
        "source_type",
        "character_id",
        "relevant_point_ids",
    }
)


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCase:
    """사람이 정답 문서를 지정한 검색 평가 질문."""

    question_id: str
    question: str
    query_type: QueryType
    case_id: str
    source_type: SourceType
    character_id: str | None
    relevant_point_ids: tuple[str, ...]


def _validate_text(
    value: object,
    field_name: str,
) -> str:
    """비어 있지 않은 문자열만 허용한다."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}은 비어 있지 않은 문자열이어야 합니다.")

    return value.strip()


def _validate_uuid(value: object) -> str:
    """평가 정답 UUID의 형식을 검증한다."""

    if not isinstance(value, str):
        raise TypeError("정답 UUID는 문자열이어야 합니다.")

    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError("정답 UUID 형식이 올바르지 않습니다.") from exc

    if str(parsed) != value:
        raise ValueError("정답 UUID는 표준 소문자 형식이어야 합니다.")

    return value


def load_retrieval_evaluation_cases(
    path: Path,
    *,
    trusted_records: Iterable[HybridChunkRecord],
) -> list[RetrievalEvaluationCase]:
    """JSONL 평가셋을 로딩하고 서버 원본 데이터와 대조한다.

    평가 정답은 반드시 신뢰할 수 있는 원본 UUID를 참조해야 한다.

    Qdrant 검색 결과를 정답 데이터로 자동 사용하지 않는다.
    """

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError("검색 평가 데이터셋 파일을 찾을 수 없습니다.")

    # 1. 서버 원본 청크 색인
    trusted_by_id: dict[str, HybridChunkRecord] = {}

    for record in trusted_records:
        if not isinstance(record, HybridChunkRecord):
            raise TypeError("신뢰 원본 청크 타입이 올바르지 않습니다.")

        point_id = record.chunk.point_id

        if point_id in trusted_by_id:
            raise ValueError("신뢰 원본에 중복 UUID가 존재합니다.")

        trusted_by_id[point_id] = record

    if not trusted_by_id:
        raise ValueError("신뢰할 수 있는 원본 청크가 없습니다.")

    # 2. 평가 데이터셋 읽기
    lines = path.read_text(encoding="utf-8-sig").splitlines()

    cases: list[RetrievalEvaluationCase] = []
    seen_question_ids: set[str] = set()

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{line_number}행 JSON 형식이 올바르지 않습니다.") from exc

        if not isinstance(raw, dict):
            raise TypeError(f"{line_number}행은 JSON 객체여야 합니다.")

        # 3. 필수 필드 및 불필요한 필드 차단
        if set(raw) != REQUIRED_FIELDS:
            raise ValueError(f"{line_number}행의 평가 필드 구성이 올바르지 않습니다.")

        question_id = _validate_text(
            raw["question_id"],
            "question_id",
        )

        if re.fullmatch(r"Q[0-9]{3,}", question_id) is None:
            raise ValueError("question_id는 Q001 형식이어야 합니다.")

        if question_id in seen_question_ids:
            raise ValueError("중복된 평가 질문 ID가 존재합니다.")

        seen_question_ids.add(question_id)

        question = _validate_text(
            raw["question"],
            "question",
        )

        case_id = _validate_text(
            raw["case_id"],
            "case_id",
        )

        # 4. 질문 유형 검증
        query_type = raw["query_type"]

        if query_type not in (
            "keyword",
            "paraphrase",
            "multi_document",
        ):
            raise ValueError("지원하지 않는 평가 질문 유형입니다.")

        # 5. 검색 대상 검증
        source_type = raw["source_type"]

        if source_type not in (
            "player_document",
            "npc_knowledge",
        ):
            raise ValueError("지원하지 않는 검색 문서 유형입니다.")

        character_id = raw["character_id"]

        if source_type == "npc_knowledge":
            character_id = _validate_text(
                character_id,
                "character_id",
            )

        elif character_id is not None:
            raise ValueError(
                "플레이어 문서 평가에는 character_id를 지정할 수 없습니다."
            )

        # 6. 정답 UUID 목록 검증
        raw_relevant = raw["relevant_point_ids"]

        if not isinstance(raw_relevant, list) or not raw_relevant:
            raise ValueError("정답 UUID가 최소 1개 필요합니다.")

        relevant_ids = tuple(_validate_uuid(point_id) for point_id in raw_relevant)

        if len(relevant_ids) != len(set(relevant_ids)):
            raise ValueError("하나의 질문에 중복된 정답 UUID가 존재합니다.")

        # 7. 실제 원본 데이터와 정답 대조
        for point_id in relevant_ids:
            record = trusted_by_id.get(point_id)

            if record is None:
                raise ValueError(
                    f"{question_id}: 원본에 존재하지 않는 정답 UUID입니다."
                )

            chunk = record.chunk

            if chunk.case_id != case_id:
                raise ValueError(f"{question_id}: 정답의 사건 ID가 다릅니다.")

            if chunk.source_type != source_type:
                raise ValueError(f"{question_id}: 정답의 문서 유형이 다릅니다.")

            if chunk.character_id != character_id:
                raise ValueError(f"{question_id}: 정답의 NPC 소유자가 다릅니다.")

        # 8. 검증된 평가 질문 저장
        cases.append(
            RetrievalEvaluationCase(
                question_id=question_id,
                question=question,
                query_type=query_type,
                case_id=case_id,
                source_type=source_type,
                character_id=character_id,
                relevant_point_ids=relevant_ids,
            )
        )

    if not cases:
        raise ValueError("검색 평가 질문이 존재하지 않습니다.")

    return cases
