"""이슈 #178 - NPC 연속 대화 및 기억 확장 평가."""

import json
import subprocess

from datetime import datetime

import evaluate_day7_npc_baseline as baseline


NPC_IDS = ("C01", "C03", "C07")

ADDITIONAL_QUESTIONS = (
    (
        "X01",
        "memory",
        "제가 처음에 어떤 이야기로 대화를 시작했는지 기억하세요?",
    ),
    (
        "X02",
        "consistency",
        "앞에서 말씀하신 신기범 씨와의 관계를 다시 설명해 주세요.",
    ),
    (
        "X03",
        "context",
        "그 사람에 대해 방금 말씀하신 내용을 좀 더 설명해 주세요.",
    ),
    (
        "X04",
        "emotion",
        "같은 질문을 계속해서 불편하신가요?",
    ),
)


def main():
    if baseline.settings.llm_provider != "openai":
        raise RuntimeError("Invalid evaluation provider")

    if baseline.settings.openai_model != "gpt-5.6-luna":
        raise RuntimeError("Baseline model mismatch")

    original = baseline.QUESTIONS

    normal = tuple(
        item for item in original
        if item[1] != "security"
    )

    security = tuple(
        item for item in original
        if item[1] == "security"
    )

    questions = normal + ADDITIONAL_QUESTIONS + security

    token = (
        baseline.LOCAL
        / "case001_1120_release/service-token.txt"
    ).read_text(encoding="utf-8-sig").strip()

    if not token:
        raise RuntimeError("Service token missing")

    output_dir = (
        baseline.LOCAL / "day8_npc_evaluation"
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / (
        f"extended-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    )

    report = {
        "evaluation_type": "extended_dialogue_fixture",
        "content_version": baseline.CONTENT_VERSION,
        "release_version": baseline.RELEASE_VERSION,
        "provider": baseline.settings.llm_provider,
        "model": baseline.settings.openai_model,
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "chapter": "CH00",
        "expected_turns": len(NPC_IDS) * len(questions),
        "complete": False,
        "results": [],
        "npc_summary": {},
        "errors": [],
    }

    def save():
        temp = output.with_suffix(".tmp")

        temp.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temp.replace(output)

    save()

    baseline.QUESTIONS = questions

    try:
        with baseline.load_expanded_release_resources(
            catalog_path=(
                baseline.LOCAL
                / "case001_1120_runtime/catalog.draft.json"
            ),
            dataset_root=(
                baseline.LOCAL / "case001_1120_rag"
            ),
            token=token,
            release_version=baseline.RELEASE_VERSION,
        ) as resources:

            if (
                resources.content_version
                != baseline.CONTENT_VERSION
            ):
                raise RuntimeError("Content version mismatch")

            for npc in NPC_IDS:
                baseline.evaluate_npc(
                    npc,
                    resources,
                    report,
                    save,
                )

        report["summary"] = baseline.summarize(
            report["results"]
        )

        report["complete"] = (
            len(report["results"]) == report["expected_turns"]
            and not report["errors"]
        )

    finally:
        baseline.QUESTIONS = original
        save()

    print("\nEXTENDED EVALUATION SUMMARY")
    print(json.dumps(report["summary"], indent=2))
    print("COMPLETE:", report["complete"])
    print("RESULT FILE:", output)

    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
