"""CASE-001 임시 검색 평가 데이터셋 생성."""

import json
from pathlib import Path

from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
)
from crimescene.retriever.retrieval_eval_dataset import (
    load_retrieval_evaluation_cases,
)

CASE_ID = "CASE-001"
EXCLUDED_IDS = {"Q027"}


def read_jsonl(path: Path) -> list[dict]:
    """JSONL 데이터를 읽고 객체 형식을 검증한다."""

    if not path.is_file():
        raise FileNotFoundError(f"파일이 존재하지 않습니다: {path.name}")

    rows = []

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue

        row = json.loads(line)

        if not isinstance(row, dict):
            raise TypeError("평가 데이터는 JSON 객체여야 합니다.")

        rows.append(row)

    return rows


def main():
    project_root = Path(__file__).resolve().parents[2]

    root = project_root / ".local" / "case001_v7_1"

    original_path = root / "retrieval_eval_draft.jsonl"
    revised_path = root / "retrieval_eval_revised.jsonl"
    output_path = root / "retrieval_eval_provisional.jsonl"

    # 1. 원본 및 수정본 로딩
    original_rows = read_jsonl(original_path)
    revised_rows = read_jsonl(revised_path)

    if len(original_rows) != 30 or len(revised_rows) != 30:
        raise ValueError("원본과 수정본 모두 30개 질문이어야 합니다.")

    # 2. 서버의 신뢰 원본 로딩
    matches = list(root.glob("*/data/access_policies.json"))

    if len(matches) != 1:
        raise ValueError("CASE-001 원본 데이터 경로가 올바르지 않습니다.")

    records = load_case001_hybrid_records(matches[0].parent)

    if len(records) != 116:
        raise ValueError("신뢰 원본 청크 개수가 올바르지 않습니다.")

    trusted_by_id = {record.chunk.point_id: record.chunk for record in records}

    if len(trusted_by_id) != 116:
        raise ValueError("신뢰 원본 UUID가 중복되었습니다.")

    # 3. 최종 평가 구조 생성
    provisional_rows = []
    seen_questions = set()

    for index, (original, revised) in enumerate(
        zip(original_rows, revised_rows, strict=True),
        start=1,
    ):
        question_id = f"Q{index:03d}"

        if (
            original.get("question_id") != question_id
            or revised.get("question_id") != question_id
        ):
            raise ValueError(f"{question_id}: 질문 ID 불일치")

        # 수정 과정에서 원본 UUID가 바뀌지 않았는지 검증
        for field in (
            "case_id",
            "source_type",
            "character_id",
            "query_type",
            "suggested_point_ids",
        ):
            if original.get(field) != revised.get(field):
                raise ValueError(f"{question_id}: {field} 변경 감지")

        if revised["case_id"] != CASE_ID:
            raise ValueError(f"{question_id}: 사건 ID 불일치")

        # Q027은 GameState 진술 단계 평가로 분리
        if question_id in EXCLUDED_IDS:
            if revised.get("review_status") != "exclude_stateful":
                raise ValueError("Q027은 상태 기반 평가로 분리되어야 합니다.")

            continue

        if revised.get("review_status") != "needs_review":
            raise ValueError(f"{question_id}: 예상하지 못한 검수 상태")

        question = revised["question"]

        if not isinstance(question, str):
            raise TypeError("평가 질문은 문자열이어야 합니다.")

        if not question.strip():
            raise ValueError(f"{question_id}: 질문이 비어 있습니다.")

        normalized = " ".join(question.split()).casefold()

        if normalized in seen_questions:
            raise ValueError(f"{question_id}: 중복된 평가 질문")

        seen_questions.add(normalized)

        relevant_ids = revised["suggested_point_ids"]

        expected_count = 2 if revised["query_type"] == "multi_document" else 1

        if len(relevant_ids) != expected_count:
            raise ValueError(f"{question_id}: 추천 UUID 개수 불일치")

        if len(set(relevant_ids)) != len(relevant_ids):
            raise ValueError(f"{question_id}: 중복된 추천 UUID")

        # 4. 추천 UUID를 신뢰 원본과 대조
        for point_id in relevant_ids:
            chunk = trusted_by_id.get(point_id)

            if chunk is None:
                raise ValueError(f"{question_id}: 원본에 없는 UUID")

            if (
                chunk.case_id != revised["case_id"]
                or chunk.source_type != revised["source_type"]
                or chunk.character_id != revised["character_id"]
            ):
                raise ValueError(f"{question_id}: 원본 메타데이터 불일치")

        # 5. 기존 평가 로더가 요구하는 필드만 저장
        provisional_rows.append(
            {
                "question_id": question_id,
                "question": question.strip(),
                "query_type": revised["query_type"],
                "case_id": revised["case_id"],
                "source_type": revised["source_type"],
                "character_id": revised["character_id"],
                "relevant_point_ids": relevant_ids,
            }
        )

    if len(provisional_rows) != 29:
        raise ValueError("임시 평가 질문은 29개여야 합니다.")

    if output_path.exists():
        raise FileExistsError("임시 평가 데이터셋이 이미 존재합니다.")

    # 6. JSONL 저장
    with output_path.open("x", encoding="utf-8") as file:
        for row in provisional_rows:
            file.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 7. 기존 데이터셋 검증 엔진으로 최종 형식 확인
    cases = load_retrieval_evaluation_cases(
        output_path,
        trusted_records=records,
    )

    assert len(cases) == 29

    counts = {
        query_type: sum(case.query_type == query_type for case in cases)
        for query_type in (
            "keyword",
            "paraphrase",
            "multi_document",
        )
    }

    print("=== RETRIEVAL EVALUATION DATASET ===")
    print("Trusted records:", len(records))
    print("Evaluation questions:", len(cases))
    print("Keyword:", counts["keyword"])
    print("Paraphrase:", counts["paraphrase"])
    print("Multi-document:", counts["multi_document"])
    print("Excluded stateful questions:", len(EXCLUDED_IDS))
    print("UUID validation: PASSED")
    print("Metadata validation: PASSED")
    print("Gold labels: NOT CONFIRMED")
    print("Output:", output_path)
    print("PROVISIONAL DATASET VALIDATION PASSED")


if __name__ == "__main__":
    main()
