"""CASE-001 실제 NPC 대화 리소스의 서버 수명주기 관리.

원본 시나리오 데이터는 서버 로컬에서만 읽고 API 응답으로 전달하지 않습니다.
"""

import json
import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from neo4j import GraphDatabase
from ollama import Client as OllamaClient
from qdrant_client import QdrantClient

from crimescene.chat.npc_persona import load_npc_personas
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.db.neo4j_ingest import load_entity_registry
from crimescene.db.neo4j_sync import find_source
from crimescene.db.qdrant_collection import COLLECTION_NAME
from crimescene.ingest.case001_dataset import (
    load_case001_hybrid_records,
    load_npc_cards,
)
from crimescene.ingest.ollama_embedder import OllamaEmbedder
from crimescene.retriever.korean_bm25 import KoreanBM25Encoder
from crimescene.scenario.evidence_acquisition import build_evidence_acquisition_setup
from crimescene.scenario.loaders.access_policy_loader import load_access_policies
from crimescene.scenario.loaders.document_loader import load_player_documents
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.loaders.relationship_loader import load_relationship_edges
from crimescene.scenario.loaders.unlock_graph_loader import (
    Case001UnlockRules,
    load_case001_unlock_rules,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.settings import settings
from crimescene.trigger.npc_trigger import NPCTriggerRule

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_ROOT = PROJECT_ROOT / ".local" / "case001_v7_1"


@dataclass(frozen=True, slots=True)
class ChatRuntime:
    resources: NPCRAGResources
    policies: dict[str, AccessPolicy]
    triggers: tuple[NPCTriggerRule, ...]
    flag_config: Case001UnlockRules | None
    acquisition_policy_ids: dict[str, str]
    acquisition_evaluator: PolicyEvaluator


def _locate_data_dir(root: Path) -> Path:
    """검증 가능한 사건 데이터 폴더만 허용합니다."""
    if not root.is_dir():
        raise FileNotFoundError(f"CASE-001 데이터 루트가 없습니다: {root}")

    if (root / "characters.json").is_file():
        data_dir = root
    else:
        found = sorted(root.glob("*/data/characters.json"))
        if len(found) != 1:
            raise FileNotFoundError(
                f"CASE-001 원본 폴더는 하나여야 합니다: {root} (발견 {len(found)}개)"
            )
        data_dir = found[0].parent

    for name in (
        "characters.json",
        "npc_knowledge_cards.jsonl",
        "player_documents.jsonl",
        "access_policies.json",
    ):
        if not (data_dir / name).is_file():
            raise FileNotFoundError(f"CASE-001 필수 원본 누락: {name}")
    return data_dir


def _optional_path(env_name: str) -> Path | None:
    value = os.environ.get(env_name)
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{env_name} 파일을 찾을 수 없습니다: {path}")
    return path


def _load_triggers(path: Path | None) -> tuple[NPCTriggerRule, ...]:
    if path is None:
        return ()
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise TypeError("NPC 트리거는 JSON 배열이어야 합니다.")
    rules = tuple(
        NPCTriggerRule.model_validate_json(json.dumps(item, ensure_ascii=False))
        for item in raw
    )
    ids = [rule.trigger_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("NPC 트리거 ID가 중복됐습니다.")
    return rules


def _load_acquisition_policies(
    path: Path | None,
    *,
    evidence_rules: dict,
    policies: dict[str, AccessPolicy],
    npc_cards: list[dict],
) -> dict[str, str]:
    """서버 관리 증거 정책만 허용합니다. 임의 정책 자동 생성은 금지합니다.

    수집하려면 해당 NPC의 실제 공개 완료 지식 카드가 있어야 합니다.
    조건을 만족하지 않는 정책은 시작 단계에서 거부합니다.
    """
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("증거 수집 정책은 비어 있지 않은 JSON 객체여야 합니다.")

    valid_cards = {
        (card.get("id"), card.get("character_id"))
        for card in npc_cards
        if isinstance(card, dict)
    }
    result: dict[str, str] = {}
    for evidence_id, policy_id in raw.items():
        if evidence_id not in evidence_rules:
            raise ValueError(f"등록되지 않은 증거 ID: {evidence_id}")
        if not isinstance(policy_id, str) or policy_id not in policies:
            raise ValueError(f"등록되지 않은 증거 획득 정책: {evidence_id}")
        rule = evidence_rules[evidence_id]
        policy = policies[policy_id]
        if policy.required_character != rule.holder:
            raise ValueError(f"증거 보유 NPC가 정책과 일치하지 않습니다: {evidence_id}")
        if not policy.required_disclosed_cards:
            raise ValueError(f"공개 지식 카드 조건이 누락됐습니다: {evidence_id}")
        if any(
            (card_id, rule.holder) not in valid_cards
            for card_id in policy.required_disclosed_cards
        ):
            raise ValueError(
                f"증거 획득 정책이 NPC의 지식 카드와 일치하지 않습니다: {evidence_id}"
            )
        result[evidence_id] = policy_id

    if len(set(result.values())) != len(result):
        raise ValueError("서로 다른 증거에는 서로 다른 획득 정책을 지정해야 합니다.")
    return result


@contextmanager
def load_chat_runtime() -> Iterator[ChatRuntime]:
    """CASE-001 원본·Qdrant·Neo4j·Ollama를 연결하고 종료 시 정리합니다."""
    if settings.llm_provider == "ollama" and not settings.ollama_model:
        raise ValueError("backend/.env 또는 환경변수에 OLLAMA_MODEL을 설정하세요.")
    if (
        settings.llm_provider == "openai"
        and not settings.openai_api_key.get_secret_value().strip()
    ):
        raise ValueError("backend/.env 또는 환경변수에 OPENAI_API_KEY를 설정하세요.")

    root = Path(
        os.getenv("CRIMESCENE_CASE001_ROOT", str(settings.crimescene_case001_root))
    ).expanduser()

    if not root.is_absolute():
        root = PROJECT_ROOT / root

    root = root.resolve()
    data_dir = _locate_data_dir(root)

    personas = load_npc_personas(data_dir / "characters.json")
    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")
    policies = load_access_policies(data_dir / "access_policies.json")
    documents = load_player_documents(data_dir / "player_documents.jsonl")
    records = load_case001_hybrid_records(data_dir)
    registry = load_entity_registry(find_source(root, "entity_registry.json"))
    edges = load_relationship_edges(find_source(root, "relationship_edges_source.json"))
    evidence_rules = load_evidence_rules(find_source(root, "evidence_rules.json"))

    actual_counts = (
        len(personas),
        len(cards),
        len(policies),
        len(evidence_rules),
        len(records),
    )
    if actual_counts != (10, 88, 153, 10, 116):
        raise ValueError(f"CASE-001 데이터 무결성 오류: {actual_counts}")

    triggers = _load_triggers(_optional_path("CRIMESCENE_TRIGGER_RULES_PATH"))
    if any(rule.policy_id not in policies for rule in triggers):
        raise ValueError("존재하지 않는 접근 정책을 참조한 트리거가 있습니다.")

    unlock_path = _optional_path("CRIMESCENE_UNLOCK_GRAPH_PATH")
    if unlock_path is None:
        # 로컬 사건 원본에서 검증된 단일 해금 규칙만 자동 로딩합니다.
        unlock_files = sorted(root.rglob("unlock_graph.json"))
        if len(unlock_files) > 1:
            raise ValueError("unlock_graph.json 파일이 여러 개입니다.")
        unlock_path = unlock_files[0] if unlock_files else None
    flags = load_case001_unlock_rules(unlock_path) if unlock_path else None

    # 이제 획득 정책은 원본 effects.find로 검증하므로 구식 수동 매핑과 병용하지 않습니다.
    if os.getenv("CRIMESCENE_ACQUISITION_POLICIES_PATH"):
        raise ValueError(
            "CRIMESCENE_ACQUISITION_POLICIES_PATH를 해제하세요. "
            "CASE-001 v7.1 원본의 effects.find에서 획득 정책을 검증합니다."
        )
    if flags is None:
        raise ValueError(
            "CASE-001 unlock_graph.json이 없어 인물 해금을 검증할 수 없습니다."
        )

    acquisition = build_evidence_acquisition_setup(
        evidence_rules=evidence_rules,
        policies=policies,
        npc_cards=cards,
    )
    acquisition_policy_ids = acquisition.policy_ids
    triggers = (*triggers, *acquisition.triggers)
    if len({rule.trigger_id for rule in triggers}) != len(triggers):
        raise ValueError("NPC 트리거 ID가 중복됐습니다.")

    with ExitStack() as stack:
        qdrant = QdrantClient(url=settings.qdrant_url, timeout=60)
        stack.callback(qdrant.close)

        neo4j = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            connection_timeout=10,
        )
        stack.callback(neo4j.close)
        neo4j.verify_connectivity()

        ollama = OllamaClient(host=settings.ollama_base_url, timeout=120)
        # 모델이 없으면 첫 번째 사용자 요청이 아니라 서버 시작 단계에서 실패합니다.
        if settings.llm_provider == "ollama":
            ollama.show(settings.ollama_model)
        ollama.show("bge-m3")

        if not qdrant.collection_exists(COLLECTION_NAME):
            raise RuntimeError(f"Qdrant 컬렉션이 없습니다: {COLLECTION_NAME}")
        points = qdrant.count(collection_name=COLLECTION_NAME, exact=True).count
        if points != len(records):
            raise RuntimeError(f"Qdrant 데이터 불일치: {points} != {len(records)}")

        resources = NPCRAGResources(
            personas=personas,
            qdrant_client=qdrant,
            neo4j_driver=neo4j,
            embedder=OllamaEmbedder(model="bge-m3", vector_size=1024, client=ollama),
            encoder=KoreanBM25Encoder(),
            trusted_records=tuple(records),
            documents=tuple(documents),
            npc_cards=tuple(cards),
            registry=tuple(registry),
            trusted_edges=tuple(edges),
            evidence_rules=evidence_rules,
            evaluator=PolicyEvaluator(policies),
        )

        # 선택적 RAG 워밍업: 실제 사건 문서는 사용하지 않습니다.
        if os.getenv("CRIMESCENE_RAG_WARMUP", "false").lower() in {
            "1", "true", "yes"
        }:
            resources.encoder.encode_query("학교 기록")
            resources.embedder.embed_query("학교 기록")
            
        yield ChatRuntime(
            resources=resources,
            policies=policies,
            triggers=triggers,
            flag_config=flags,
            acquisition_policy_ids=acquisition_policy_ids,
            acquisition_evaluator=acquisition.evaluator,
        )
