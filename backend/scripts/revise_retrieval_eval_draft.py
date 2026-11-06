"""CASE-001 검색 평가 질문을 실제 플레이어 대화체로 수정한다."""

import json
from pathlib import Path

REVISIONS = {
    "Q001": "2016년 10월 지출결의서에서 서미란의 결재 서명이 빠져 있었나요?",
    "Q002": "21시 25분에 비상계단 쪽으로 가던 사람을 봤다는 게 누구예요?",
    "Q003": "백서윤이 23시 40분에 나갔다는 기록은 정확히 뭐라고 적혀 있나요?",
    "Q004": "2017년 공사 이후 북측 배수시설의 옛 점검 공간은 도면에서 어떻게 표시됐나요?",
    "Q007": "신기범 사무실에서 발견한 봉투에는 뭐라고 적혀 있었어요? 안에 든 내용도 공개됐나요?",
    "Q008": "21시 04분에 공용 카드 #3이 사용됐다는 기록에서 확인되는 정보와 가려진 정보는 뭐예요?",
    "Q009": "22시 27분 북측 통로 영상에 찍힌 두 사람이 누구인지 확인됐나요?",
    "Q010": "후지이 류의 캠코더에는 뭐가 찍혔어요? 사람 얼굴도 알아볼 수 있나요?",
    "Q011": "그날 서류철을 들고 올라갔다고 하셨죠? 가방에 뭐가 있었는지는 어떻게 답하셨어요?",
    "Q012": "저녁 8시 반부터 어디서 뭘 하셨어요? 신기범 씨는 만났나요?",
    "Q015": "그날 7시쯤 신기범은 어떤 상태였어요? 무슨 말을 했나요?",
    "Q016": "그 사람이 다음 날 문제를 신고하겠다고 했을 때 뭐라고 권하셨어요?",
    "Q017": "'가만있지 않겠다'는 말은 무슨 뜻이었나요? 정말 계약 문제 때문이었어요?",
    "Q018": "처음에는 왜 사건 관련 자료를 피했어요? 공식 수사에서는 무엇을 증언하겠다고 했나요?",
    "Q019": "통금 후 찍은 영상을 왜 공개하기 어려웠나요? 구체적인 이유도 말씀하셨나요?",
    "Q020": "그날 본관에 몇 시에 들어갔다 나왔어요? 그다음엔 어디 있었죠?",
    "Q021": "장학금 결재 서류와 출문대장 수정 기록에서 윤태식의 승인 흔적은 각각 어떻게 나타났나요?",
    "Q022": "2016년 서윤이가 난간 아래로 사라졌을 때 기범이는 어떻게 했고, 2026년 기범이 사건 현장에서는 무엇이 발견됐나요?",
    "Q023": "캠코더는 몇 시쯤 촬영됐고, 영상에 찍힌 두 사람의 신원을 확인할 수 있나요?",
    "Q025": "서윤이가 장학금 정산을 의심한 이유가 뭔가요? 학교는 차액 4천만 원을 어떤 항목으로 처리했다고 했죠?",
    "Q026": "서윤이가 위험한 일을 조사한다는 얘기를 언제 선생님께 전했어요? 왜 그런 행동을 했나요?",
    "Q028": "박도현이 카드를 확인하러 온 건 몇 시고, 백업 사본은 몇 시에 보관했나요? 시간 차이는 얼마나 되죠?",
    "Q029": "20시 28분에 본관에서 나온 뒤 어디 있었나요? 그 전에 있었던 언쟁은 어떻게 설명했죠?",
}

EXCLUDED_QUESTION = "Q027"


def main():
    # 실행 위치와 관계없이 프로젝트 루트를 찾는다.
    project_root = Path(__file__).resolve().parents[2]

    data_dir = project_root / ".local" / "case001_v7_1"

    input_path = data_dir / "retrieval_eval_draft.jsonl"
    output_path = data_dir / "retrieval_eval_revised.jsonl"

    if not input_path.is_file():
        raise FileNotFoundError("원본 평가 질문 파일을 찾을 수 없습니다.")

    if output_path.exists():
        raise FileExistsError("수정본이 이미 있습니다. 덮어쓰지 않습니다.")

    rows = []

    for line in input_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue

        row = json.loads(line)

        if not isinstance(row, dict):
            raise TypeError("평가 질문은 JSON 객체여야 합니다.")

        rows.append(row)

    if len(rows) != 30:
        raise ValueError(f"질문은 30개여야 합니다. 현재 {len(rows)}개입니다.")

    expected_ids = {f"Q{index:03d}" for index in range(1, 31)}

    actual_ids = [row.get("question_id") for row in rows]

    if len(set(actual_ids)) != 30 or set(actual_ids) != expected_ids:
        raise ValueError("질문 ID가 누락되었거나 중복됐습니다.")

    if len(REVISIONS) != 23:
        raise ValueError("수정 대상 질문은 23개여야 합니다.")

    revised = 0
    unchanged = 0
    excluded = 0

    for row in rows:
        question_id = row["question_id"]

        # 원본 질문 보존
        row["original_question"] = row["question"]

        if question_id == EXCLUDED_QUESTION:
            row["review_status"] = "exclude_stateful"

            row["review_note"] = (
                "초기 진술과 후속 진술의 공개 단계가 달라 "
                "일반 검색 평가에서 제외하고 "
                "GameState 기반 테스트로 분리합니다."
            )

            excluded += 1

        elif question_id in REVISIONS:
            row["question"] = REVISIONS[question_id]
            row["review_status"] = "needs_review"
            row["review_note"] = (
                "자연어 질문 수정 완료. 정답 UUID의 적합성은 추가 검수 필요."
            )

            revised += 1

        else:
            row["review_status"] = "needs_review"
            row["review_note"] = "기존 질문 유지. 정답 적합성 최종 검수 필요."

            unchanged += 1

    # JSONL 수정본 생성
    with output_path.open("x", encoding="utf-8") as file:
        for row in rows:
            file.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    print("=== EVALUATION REVISION ===")
    print("Total questions:", len(rows))
    print("Revised:", revised)
    print("Unchanged:", unchanged)
    print("Excluded from general retrieval:", excluded)
    print("Gold labels: NOT CONFIRMED")
    print("Output:", output_path)

    assert revised == 23
    assert unchanged == 6
    assert excluded == 1

    print("EVALUATION REVISION PASSED")


if __name__ == "__main__":
    main()
