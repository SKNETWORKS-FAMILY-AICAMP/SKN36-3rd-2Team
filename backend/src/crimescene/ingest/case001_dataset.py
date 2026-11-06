"""CASE-001 실제 데이터를 RAG 청크로 로딩한다."""

import json
from pathlib import Path

from crimescene.ingest.chunking_config import ChunkingConfig
from crimescene.ingest.hybrid_chunker import (
    HybridChunkRecord,
    build_hybrid_chunks,
)
from crimescene.ingest.npc_knowledge_chunker import (
    build_npc_knowledge_chunks,
)
from crimescene.ingest.player_document_chunker import (
    build_player_document_chunks,
)
from crimescene.ingest.semantic_chunker import EmbeddingFunction
from crimescene.scenario.loaders.access_policy_loader import (
    load_access_policies,
)
from crimescene.scenario.loaders.document_loader import (
    load_player_documents,
)

CASE_ID = "CASE-001"


def load_npc_cards(path: Path) -> list[dict]:
    """NPC 지식 카드 JSONL 파일을 읽는다."""

    cards = []

    with path.open(encoding="utf-8-sig") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                card = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"NPC JSON 파싱 실패: line={line_number}") from exc

            if not isinstance(card, dict):
                raise TypeError(f"NPC 카드 형식 오류: line={line_number}")

            cards.append(card)

    if not cards:
        raise ValueError("NPC 지식 카드가 비어 있습니다.")

    return cards


def load_case001_hybrid_records(
    data_dir: Path,
    *,
    config: ChunkingConfig | None = None,
    embed_sentences: EmbeddingFunction | None = None,
) -> list[HybridChunkRecord]:
    """CASE-001 문서와 NPC 지식을 Hybrid 청크로 변환한다.

    원본 파일은 읽기 전용으로 사용한다.
    접근 정책을 검증하지만, 플레이어 공개 권한을 승인하지는 않는다.
    """

    if not data_dir.is_dir():
        raise FileNotFoundError(f"CASE-001 데이터 폴더가 없습니다: {data_dir}")

    # 1. 접근 정책 로딩
    policies = load_access_policies(data_dir / "access_policies.json")

    valid_policy_ids = set(policies)

    # 2. 플레이어 문서 로딩
    documents = load_player_documents(data_dir / "player_documents.jsonl")

    # 3. NPC 지식 카드 로딩
    cards = load_npc_cards(data_dir / "npc_knowledge_cards.jsonl")

    # 4. 플레이어 문서 청킹
    document_chunks = build_player_document_chunks(
        documents,
        expected_case_id=CASE_ID,
        valid_policy_ids=valid_policy_ids,
    )

    # 5. NPC 지식 카드 청킹
    npc_chunks = build_npc_knowledge_chunks(
        cards,
        expected_case_id=CASE_ID,
        valid_policy_ids=valid_policy_ids,
    )

    # 6. 원본 청크 결합
    source_chunks = document_chunks + npc_chunks

    # 7. Hybrid Chunking
    records = build_hybrid_chunks(
        source_chunks,
        config if config is not None else ChunkingConfig(),
        embed_sentences=embed_sentences,
    )

    # 8. 전체 UUID 중복 검증
    point_ids = [record.chunk.chunk_id for record in records]

    if len(point_ids) != len(set(point_ids)):
        raise ValueError("중복된 Qdrant Point UUID가 존재합니다.")

    return records
