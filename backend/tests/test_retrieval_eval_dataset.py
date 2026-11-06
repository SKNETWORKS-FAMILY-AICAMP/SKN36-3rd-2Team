"""검색 평가 데이터셋 JSONL 로더 단위 테스트."""

import json
from dataclasses import FrozenInstanceError
from uuid import NAMESPACE_URL, uuid5

import pytest

from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.hybrid_chunker import HybridChunkRecord
from crimescene.retriever.retrieval_eval_dataset import (
    RetrievalEvaluationCase,
    load_retrieval_evaluation_cases,
)

CASE_ID = "CASE-001"


def make_record(
    source_id,
    *,
    source_type="player_document",
    character_id=None,
    case_id=CASE_ID,
):
    """가상의 신뢰 RAG 청크를 생성한다."""

    point_uuid = uuid5(
        NAMESPACE_URL,
        f"{case_id}:{source_type}:{source_id}",
    )

    is_npc = source_type == "npc_knowledge"

    chunk = RAGChunk(
        chunk_id=point_uuid,
        source_id=source_id,
        source_type=source_type,
        case_id=case_id,
        policy_id="POL-TEST",
        family="npc_knowledge" if is_npc else "evidence",
        access_scope=("character_only" if is_npc else "collected_evidence"),
        character_id=character_id,
        incident_year=2016,
        content_hash=f"hash-{source_id}",
        search_text=f"{source_id} 가상 검색 문서",
        body=f"{source_id} 가상 테스트 내용",
    )

    return HybridChunkRecord(
        chunk=chunk,
        parent_point_id=point_uuid,
        chunk_index=0,
        chunk_count=1,
    )


@pytest.fixture
def records():
    """서버가 관리하는 가상의 신뢰 원본."""

    return [
        make_record("DOC-001"),
        make_record("DOC-002"),
        make_record(
            "K-C01-001",
            source_type="npc_knowledge",
            character_id="C01",
        ),
        make_record(
            "K-C02-001",
            source_type="npc_knowledge",
            character_id="C02",
        ),
        make_record(
            "DOC-OUTSIDE",
            case_id="CASE-999",
        ),
    ]


def make_row(record, *, question_id="Q001", **overrides):
    """신뢰 원본을 참조하는 평가 질문을 생성한다."""

    chunk = record.chunk

    row = {
        "question_id": question_id,
        "question": "사건 관련 기록은 어디에 있나요?",
        "query_type": "keyword",
        "case_id": chunk.case_id,
        "source_type": chunk.source_type,
        "character_id": chunk.character_id,
        "relevant_point_ids": [chunk.point_id],
    }

    row.update(overrides)

    return row


def write_rows(tmp_path, rows, *, bom=False):
    """테스트용 JSONL 파일을 생성한다."""

    path = tmp_path / "retrieval_eval.jsonl"

    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)

    if bom:
        content = "\ufeff" + content

    path.write_text(
        content + "\n",
        encoding="utf-8",
    )

    return path


def load_rows(tmp_path, records, *rows):
    """JSONL 파일을 생성한 뒤 평가 로더를 실행한다."""

    path = write_rows(tmp_path, rows)

    return load_retrieval_evaluation_cases(
        path,
        trusted_records=records,
    )


def test_valid_player_document(tmp_path, records):
    """정상 플레이어 문서 평가 질문을 로딩한다."""

    result = load_rows(
        tmp_path,
        records,
        make_row(records[0]),
    )

    assert len(result) == 1

    case = result[0]

    assert isinstance(case, RetrievalEvaluationCase)
    assert case.question_id == "Q001"
    assert case.source_type == "player_document"
    assert case.character_id is None

    assert case.relevant_point_ids == (records[0].chunk.point_id,)


def test_valid_npc_knowledge(tmp_path, records):
    """정상 NPC 지식 평가 질문을 로딩한다."""

    result = load_rows(
        tmp_path,
        records,
        make_row(
            records[2],
            query_type="paraphrase",
        ),
    )

    assert len(result) == 1
    assert result[0].source_type == "npc_knowledge"
    assert result[0].character_id == "C01"
    assert result[0].query_type == "paraphrase"


def test_multiple_relevant_documents(tmp_path, records):
    """하나의 질문에 정답 문서 여러 개를 지정할 수 있다."""

    relevant_ids = [
        records[0].chunk.point_id,
        records[1].chunk.point_id,
    ]

    result = load_rows(
        tmp_path,
        records,
        make_row(
            records[0],
            query_type="multi_document",
            relevant_point_ids=relevant_ids,
        ),
    )

    assert result[0].relevant_point_ids == tuple(relevant_ids)


def test_multiple_questions(tmp_path, records):
    """여러 평가 질문의 순서를 유지한다."""

    result = load_rows(
        tmp_path,
        records,
        make_row(records[0], question_id="Q001"),
        make_row(records[1], question_id="Q002"),
        make_row(records[2], question_id="Q003"),
    )

    assert [case.question_id for case in result] == [
        "Q001",
        "Q002",
        "Q003",
    ]


def test_utf8_bom_and_blank_lines(tmp_path, records):
    """UTF-8 BOM과 빈 줄을 정상 처리한다."""

    path = write_rows(
        tmp_path,
        [
            make_row(records[0], question_id="Q001"),
            make_row(records[1], question_id="Q002"),
        ],
        bom=True,
    )

    content = path.read_text(encoding="utf-8")

    content = content.replace(
        "\n",
        "\n\n",
    )

    path.write_text(
        content,
        encoding="utf-8",
    )

    result = load_retrieval_evaluation_cases(
        path,
        trusted_records=records,
    )

    assert len(result) == 2


def test_evaluation_case_is_immutable(tmp_path, records):
    """검증된 평가 질문을 임의로 수정할 수 없다."""

    result = load_rows(
        tmp_path,
        records,
        make_row(records[0]),
    )

    with pytest.raises(FrozenInstanceError):
        result[0].question_id = "Q999"


def test_other_case_valid_when_source_matches(
    tmp_path,
    records,
):
    """신뢰 원본의 사건 ID와 일치하면 다른 사건도 검증 가능하다."""

    result = load_rows(
        tmp_path,
        records,
        make_row(records[4]),
    )

    assert result[0].case_id == "CASE-999"


def test_missing_file(tmp_path, records):
    """존재하지 않는 평가 파일을 차단한다."""

    path = tmp_path / "missing.jsonl"

    with pytest.raises(FileNotFoundError):
        load_retrieval_evaluation_cases(
            path,
            trusted_records=records,
        )


def test_empty_dataset(tmp_path, records):
    """평가 질문이 없으면 오류를 발생시킨다."""

    with pytest.raises(
        ValueError,
        match="평가 질문이 존재하지 않습니다",
    ):
        load_rows(
            tmp_path,
            records,
        )


def test_invalid_json(tmp_path, records):
    """잘못된 JSON 형식을 차단한다."""

    path = tmp_path / "invalid.jsonl"

    path.write_text(
        '{"question_id": "Q001",',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="JSON 형식",
    ):
        load_retrieval_evaluation_cases(
            path,
            trusted_records=records,
        )


def test_json_error_line_number(tmp_path, records):
    """JSON 오류가 발생한 행 번호를 표시한다."""

    path = tmp_path / "invalid_line.jsonl"

    first_line = json.dumps(
        make_row(records[0]),
        ensure_ascii=False,
    )

    path.write_text(
        first_line + "\n{invalid json}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="2행 JSON 형식",
    ):
        load_retrieval_evaluation_cases(
            path,
            trusted_records=records,
        )


def test_non_object_json_rejected(tmp_path, records):
    """JSON 객체가 아닌 배열을 차단한다."""

    with pytest.raises(
        TypeError,
        match="JSON 객체",
    ):
        load_rows(
            tmp_path,
            records,
            ["Q001", "테스트 질문"],
        )


def test_missing_required_field(tmp_path, records):
    """필수 평가 필드 누락을 차단한다."""

    row = make_row(records[0])

    del row["question"]

    with pytest.raises(
        ValueError,
        match="필드 구성",
    ):
        load_rows(
            tmp_path,
            records,
            row,
        )


def test_unexpected_field_rejected(tmp_path, records):
    """허용하지 않은 필드를 차단한다."""

    row = make_row(records[0])

    row["admin_secret"] = "FORGED"

    with pytest.raises(
        ValueError,
        match="필드 구성",
    ):
        load_rows(
            tmp_path,
            records,
            row,
        )


def test_duplicate_question_id(tmp_path, records):
    """중복 평가 질문 ID를 차단한다."""

    with pytest.raises(
        ValueError,
        match="중복된 평가 질문 ID",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(records[0], question_id="Q001"),
            make_row(records[1], question_id="Q001"),
        )


@pytest.mark.parametrize(
    "question_id",
    [
        "",
        "Q1",
        "X001",
        "Q00A",
    ],
)
def test_invalid_question_id(
    tmp_path,
    records,
    question_id,
):
    """질문 ID 형식 오류를 차단한다."""

    with pytest.raises(ValueError):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                question_id=question_id,
            ),
        )


@pytest.mark.parametrize(
    "question",
    [
        "",
        "   ",
        None,
    ],
)
def test_invalid_question(
    tmp_path,
    records,
    question,
):
    """빈 질문과 잘못된 질문을 차단한다."""

    with pytest.raises(ValueError):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                question=question,
            ),
        )


def test_invalid_case_id(tmp_path, records):
    """빈 사건 ID를 차단한다."""

    with pytest.raises(
        ValueError,
        match="case_id",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                case_id=" ",
            ),
        )


def test_invalid_query_type(tmp_path, records):
    """지원하지 않는 질문 유형을 차단한다."""

    with pytest.raises(
        ValueError,
        match="질문 유형",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                query_type="unknown",
            ),
        )


def test_invalid_source_type(tmp_path, records):
    """지원하지 않는 문서 유형을 차단한다."""

    with pytest.raises(
        ValueError,
        match="문서 유형",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                source_type="admin_document",
            ),
        )


@pytest.mark.parametrize(
    "character_id",
    [
        None,
        "",
        "   ",
    ],
)
def test_npc_character_required(
    tmp_path,
    records,
    character_id,
):
    """NPC 지식 평가에는 인물 ID가 필요하다."""

    with pytest.raises(
        ValueError,
        match="character_id",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[2],
                character_id=character_id,
            ),
        )


def test_player_document_character_rejected(
    tmp_path,
    records,
):
    """플레이어 문서 평가에 NPC ID를 지정할 수 없다."""

    with pytest.raises(
        ValueError,
        match="character_id",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                character_id="C01",
            ),
        )


@pytest.mark.parametrize(
    "relevant_ids",
    [
        [],
        None,
        "invalid",
    ],
)
def test_invalid_relevant_ids(
    tmp_path,
    records,
    relevant_ids,
):
    """정답 UUID 목록이 없거나 형식이 잘못되면 차단한다."""

    with pytest.raises(
        ValueError,
        match="정답 UUID가 최소 1개",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                relevant_point_ids=relevant_ids,
            ),
        )


def test_duplicate_relevant_uuid(tmp_path, records):
    """한 질문에 동일 UUID를 중복 지정할 수 없다."""

    point_id = records[0].chunk.point_id

    with pytest.raises(
        ValueError,
        match="중복된 정답 UUID",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                relevant_point_ids=[
                    point_id,
                    point_id,
                ],
            ),
        )


def test_invalid_uuid_format(tmp_path, records):
    """UUID 형식이 올바르지 않으면 차단한다."""

    with pytest.raises(
        ValueError,
        match="UUID 형식",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                relevant_point_ids=["not-a-uuid"],
            ),
        )


def test_non_string_uuid_rejected(tmp_path, records):
    """문자열이 아닌 UUID를 차단한다."""

    with pytest.raises(
        TypeError,
        match="UUID는 문자열",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                relevant_point_ids=[123],
            ),
        )


def test_noncanonical_uuid_rejected(tmp_path, records):
    """표준 소문자 형식이 아닌 UUID를 차단한다."""

    uppercase_uuid = records[0].chunk.point_id.upper()

    with pytest.raises(
        ValueError,
        match="표준 소문자 형식",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                relevant_point_ids=[uppercase_uuid],
            ),
        )


def test_unknown_uuid_rejected(tmp_path, records):
    """실제 원본에 없는 UUID를 차단한다."""

    unknown_uuid = str(uuid5(NAMESPACE_URL, "UNKNOWN-DOCUMENT"))

    with pytest.raises(
        ValueError,
        match="원본에 존재하지 않는 정답 UUID",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                relevant_point_ids=[unknown_uuid],
            ),
        )


def test_case_id_mismatch(tmp_path, records):
    """정답 문서와 평가 질문의 사건 ID 불일치를 차단한다."""

    with pytest.raises(
        ValueError,
        match="사건 ID가 다릅니다",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                case_id="CASE-999",
            ),
        )


def test_source_type_mismatch(tmp_path, records):
    """정답 문서의 유형이 다르면 차단한다."""

    with pytest.raises(
        ValueError,
        match="문서 유형이 다릅니다",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[0],
                source_type="npc_knowledge",
                character_id="C01",
            ),
        )


def test_npc_owner_mismatch(tmp_path, records):
    """정답 NPC의 소유자 불일치를 차단한다."""

    with pytest.raises(
        ValueError,
        match="NPC 소유자가 다릅니다",
    ):
        load_rows(
            tmp_path,
            records,
            make_row(
                records[2],
                character_id="C02",
            ),
        )


def test_empty_trusted_records(tmp_path, records):
    """신뢰 원본이 없으면 평가 데이터를 로딩하지 않는다."""

    path = write_rows(
        tmp_path,
        [make_row(records[0])],
    )

    with pytest.raises(
        ValueError,
        match="신뢰할 수 있는 원본 청크",
    ):
        load_retrieval_evaluation_cases(
            path,
            trusted_records=[],
        )


def test_invalid_trusted_record_type(tmp_path, records):
    """신뢰 원본에 잘못된 객체가 포함되면 차단한다."""

    path = write_rows(
        tmp_path,
        [make_row(records[0])],
    )

    with pytest.raises(
        TypeError,
        match="신뢰 원본 청크 타입",
    ):
        load_retrieval_evaluation_cases(
            path,
            trusted_records=[object()],
        )


def test_duplicate_trusted_uuid(tmp_path, records):
    """서버 원본의 UUID 중복을 차단한다."""

    path = write_rows(
        tmp_path,
        [make_row(records[0])],
    )

    with pytest.raises(
        ValueError,
        match="중복 UUID",
    ):
        load_retrieval_evaluation_cases(
            path,
            trusted_records=[
                records[0],
                records[0],
            ],
        )
