"""Issue #22 - 실제 Ollama NPC 페르소나 응답 비교.

실제 CASE-001 NPC 10명의 말투와 행동을 동일한 질문으로 평가한다.

주의:
    - 개발 전용 평가 스크립트다.
    - 사건 정보나 비공개 지식은 LLM에 전달하지 않는다.
    - 실제 게임 대화에는 #20 RAG 보안 게이트가 필요하다.
"""

import argparse
from pathlib import Path

from crimescene.chat.llm_client import generate_response
from crimescene.chat.npc_behavior import build_npc_behavior_prompt
from crimescene.chat.npc_persona import (
    EXPECTED_CHARACTER_IDS,
    load_npc_personas,
)
from crimescene.chat.npc_social_style import build_social_personas
from crimescene.ingest.case001_dataset import load_npc_cards
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.game_state import GameState

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / ".local" / "case001_v7_1"

# 사건 정보를 요구하지 않는 공통 질문만 사용한다.
QUESTION = "안녕하세요. 잠깐 이야기 나눌 수 있을까요?"

SAFETY_RULES = """
[평가 전용 추가 규칙]
이 대화는 인물의 말투를 평가하기 위한 테스트입니다.
사건, 증거, 관계, 과거 행적, 비밀에 관한 사실을 언급하지 마세요.
새로운 사건 정보를 만들어내지 마세요.
현재 인물의 고유한 말투를 사용해 한두 문장으로 대답하세요.
""".strip()


def find_source() -> Path:
    """실제 CASE-001 원본 디렉터리를 찾는다."""

    matches = list(DATA_ROOT.glob("*/data/characters.json"))

    if len(matches) != 1:
        raise FileNotFoundError("CASE-001 characters.json 경로를 확인하세요.")

    data_dir = matches[0].parent

    required_files = (
        "characters.json",
        "npc_knowledge_cards.jsonl",
        "access_policies.json",
    )

    for filename in required_files:
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(f"필수 데이터가 없습니다: {filename}")

    return data_dir


def make_state() -> GameState:
    """실험을 위해 NPC 10명을 해금한 임시 게임 상태."""

    return GameState(
        case_id="CASE-001",
        session_id="ISSUE-22-PERSONA-EVALUATION",
        unlocked_characters=sorted(EXPECTED_CHARACTER_IDS),
        evidence={},
        flags=[],
        presented={},
        attempts_left=3,
        score=0,
        outcome="ONGOING",
        deep_eligible=False,
        revision=0,
        disclosed_cards=[],
        document_grants=[],
    )


def evaluate_npc_personas(repeat: int = 1) -> None:
    """실제 NPC 10명의 응답을 같은 질문으로 비교한다."""

    if not 1 <= repeat <= 3:
        raise ValueError("반복 횟수는 1~3이어야 합니다.")

    data_dir = find_source()

    # 1. 실제 인물 프로필
    personas = load_npc_personas(data_dir / "characters.json")

    # 2. 실제 NPC 지식 카드
    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")

    # 3. 실제 접근 정책
    policies = load_access_policies(data_dir / "access_policies.json")

    evaluator = PolicyEvaluator(policies)
    state = make_state()

    print("=" * 65)
    print("ISSUE #22 - NPC PERSONA EVALUATION")
    print("=" * 65)

    print(f"NPC: {len(personas)}")
    print(f"Knowledge cards: {len(cards)}")
    print(f"Access policies: {len(policies)}")
    print(f"Question: {QUESTION}")
    print(f"Repeat: {repeat}")

    print("=" * 65)

    results: dict[str, list[str]] = {}
    failures: list[str] = []

    # 4. NPC 10명 순차 평가
    for npc_id in sorted(EXPECTED_CHARACTER_IDS):
        persona = personas[npc_id]

        # 실제 원본에서 일상 대화용 말투만 분리
        social_personas = build_social_personas(
            personas,
            active_character_id=npc_id,
        )

        system_prompt = build_npc_behavior_prompt(
            social_personas,
            active_character_id=npc_id,
            state=state,
            npc_cards=cards,
            evaluator=evaluator,
        )

        print()
        print("-" * 65)
        print(f"[{npc_id}] {persona.name}")
        print(f"말투 설정: {persona.voice}")
        print("-" * 65)

        responses = []

        responses = []

        for trial in range(1, repeat + 1):
            try:
                answer = generate_response(
                    user_message=QUESTION,
                    system_prompt=system_prompt,
                )

                answer = answer.strip()

                if not answer:
                    raise ValueError("LLM 응답이 비어 있습니다.")

                responses.append(answer)

                print(f"[응답 {trial}]")
                print(answer)

            except Exception as exc:  # noqa: BLE001
                # NPC 하나가 실패해도 나머지 NPC 평가는 계속 진행
                failures.append(npc_id)

                print(f"[ERROR] {npc_id}: {type(exc).__name__}: {exc}")
                break

        results[npc_id] = responses

    # 5. 결과 요약
    print()
    print("=" * 65)
    print("EVALUATION SUMMARY")
    print("=" * 65)

    successful = sum(len(responses) == repeat for responses in results.values())

    print(f"전체 NPC: {len(personas)}")
    print(f"응답 완료: {successful}")
    print(f"실패 NPC: {len(set(failures))}")

    all_responses = [
        response for responses in results.values() for response in responses
    ]

    print(f"전체 응답: {len(all_responses)}")
    print(f"고유 응답: {len(set(all_responses))}")

    if failures:
        print(f"오류 발생 NPC: {', '.join(sorted(set(failures)))}")

    print()
    print("확인할 항목:")
    print("1. NPC마다 말투가 다른가?")
    print("2. 설정된 성격과 태도가 유지되는가?")
    print("3. 시나리오에 없는 사건 정보를 만들어내지 않는가?")
    print("4. 과거·비밀·증거에 관한 내용을 언급하지 않는가?")
    print("5. 반복 실행 시 말투와 성격이 일관적인가?")

    print()
    print("주의: 고유 응답 수는 품질 점수가 아닙니다.")
    print("실제 답변의 적절성과 정보 유출 여부는 별도 평가가 필요합니다.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CASE-001 NPC 10명 Ollama 페르소나 평가"
    )

    parser.add_argument(
        "--repeat",
        type=int,
        choices=(1, 2, 3),
        default=1,
        help="NPC별 동일 질문 반복 횟수",
    )

    args = parser.parse_args()

    evaluate_npc_personas(repeat=args.repeat)


if __name__ == "__main__":
    main()
