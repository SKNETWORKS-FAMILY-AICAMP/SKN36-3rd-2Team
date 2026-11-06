"""CASE-001 검색 평가 질문 검수 보고서 생성."""

import json
from collections import Counter
from pathlib import Path

from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
)

EXPECTED_COUNTS = {
    "keyword": 10,
    "paraphrase": 10,
    "multi_document": 10,
}


def main():
    root = Path.cwd().parent / ".local" / "case001_v7_1"

    matches = list(root.glob("*/data/access_policies.json"))

    if len(matches) != 1:
        raise ValueError("CASE-001 원본 경로를 확인하세요.")

    # 신뢰할 수 있는 원본 로딩
    records = load_case001_hybrid_records(matches[0].parent)

    assert len(records) == 116

    record_by_id = {record.chunk.point_id: record for record in records}

    assert len(record_by_id) == 116

    # 생성된 평가 질문 로딩
    draft_path = root / "retrieval_eval_draft.jsonl"

    rows = [
        json.loads(line)
        for line in draft_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]

    if len(rows) != 30:
        raise ValueError(f"평가 질문은 30개여야 합니다. 현재: {len(rows)}")

    counts = Counter(row["query_type"] for row in rows)

    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError(f"평가 질문 유형별 개수 불일치: {dict(counts)}")

    report = [
        "# CASE-001 검색 평가 질문 검수",
        "",
        "> 이 파일은 비공개 사건 정보를 포함합니다.",
        "> GitHub에 커밋하지 마세요.",
        "",
        "## 검수 기준",
        "",
        "- [ ] 질문이 실제 문서에 근거하는가?",
        "- [ ] 자연스러운 한국어 질문인가?",
        "- [ ] 추천 UUID가 실제 정답 문서인가?",
        "- [ ] 다른 문서도 정답에 포함되어야 하는가?",
        "- [ ] Multi-document는 두 문서 모두 필요한가?",
        "",
        "---",
        "",
    ]

    seen_ids = set()
    seen_questions = set()
    duplicate_questions = 0

    for index, row in enumerate(rows, start=1):
        question_id = row["question_id"]
        question = row["question"]
        query_type = row["query_type"]

        if question_id != f"Q{index:03d}":
            raise ValueError("질문 ID 순서가 잘못됐습니다.")

        if question_id in seen_ids:
            raise ValueError("질문 ID가 중복됐습니다.")

        seen_ids.add(question_id)

        normalized_question = " ".join(question.split()).casefold()

        if normalized_question in seen_questions:
            duplicate_questions += 1
            duplicate = True
        else:
            duplicate = False

        seen_questions.add(normalized_question)

        suggested_ids = row["suggested_point_ids"]

        expected_count = 2 if query_type == "multi_document" else 1

        if len(suggested_ids) != expected_count:
            raise ValueError(f"{question_id}: 정답 후보 개수 오류")

        if len(suggested_ids) != len(set(suggested_ids)):
            raise ValueError(f"{question_id}: 정답 UUID 중복")

        source_records = []

        for point_id in suggested_ids:
            record = record_by_id.get(point_id)

            if record is None:
                raise ValueError(f"{question_id}: 원본에 없는 UUID")

            chunk = record.chunk

            if (
                chunk.case_id != row["case_id"]
                or chunk.source_type != row["source_type"]
                or chunk.character_id != row["character_id"]
            ):
                raise ValueError(f"{question_id}: 정답 문서 메타데이터 불일치")

            source_records.append(record)

        report.extend(
            [
                f"## {question_id}",
                "",
                f"**유형:** {query_type}",
                "",
                f"**질문:** {question}",
                "",
            ]
        )

        if duplicate:
            report.extend(
                [
                    "⚠️ 다른 평가 질문과 내용이 중복됩니다.",
                    "",
                ]
            )

        for source_index, record in enumerate(
            source_records,
            start=1,
        ):
            chunk = record.chunk

            report.extend(
                [
                    f"### 추천 정답 문서 {source_index}",
                    "",
                    f"- Source ID: `{chunk.source_id}`",
                    f"- UUID: `{chunk.point_id}`",
                    f"- Source Type: `{chunk.source_type}`",
                    f"- Character: `{chunk.character_id}`",
                    "",
                    "**원본 내용:**",
                    "",
                ]
            )

            for line in chunk.body.splitlines():
                report.append(f"> {line}")

            report.extend(["", ""])

        report.extend(
            [
                "### 검수 결과",
                "",
                "- [ ] 질문 내용이 원본에 근거함",
                "- [ ] 추천 정답 UUID가 적절함",
                "- [ ] 질문이 자연스럽고 중복되지 않음",
                "- [ ] 다중 문서라면 두 문서 모두 필요함",
                "",
                "**판정:** 미검수",
                "",
                "---",
                "",
            ]
        )

    output_path = root / "retrieval_eval_review.md"

    # 기존 검수 보고서는 덮어쓰지 않는다.
    if output_path.exists():
        raise FileExistsError("검수 보고서가 이미 있습니다. 기존 파일을 확인하세요.")

    output_path.write_text(
        "\n".join(report),
        encoding="utf-8",
    )

    print("=== RETRIEVAL EVALUATION REVIEW ===")
    print("Trusted records:", len(records))
    print("Questions:", len(rows))
    print("Keyword:", counts["keyword"])
    print("Paraphrase:", counts["paraphrase"])
    print("Multi-document:", counts["multi_document"])
    print("Duplicate questions:", duplicate_questions)
    print("Review status: NEEDS REVIEW")
    print("Report:", output_path)
    print("EVALUATION REVIEW REPORT PASSED")


if __name__ == "__main__":
    main()
