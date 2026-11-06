from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID, uuid5

from crimescene.ingest.chunk_models import RAGChunk
from crimescene.ingest.chunking_config import ChunkingConfig, ChunkingMode
from crimescene.ingest.fixed_chunker import split_fixed_text
from crimescene.ingest.semantic_chunker import (
    EmbeddingFunction,
    split_semantic_text,
)


@dataclass(frozen=True, slots=True)
class HybridChunkRecord:
    """원본과 분할 위치를 추적할 수 있는 청크 결과."""

    chunk: RAGChunk
    parent_point_id: UUID
    chunk_index: int
    chunk_count: int


def _split_chunk_text(
    chunk: RAGChunk,
    config: ChunkingConfig,
    embed_sentences: EmbeddingFunction | None,
) -> list[str]:
    """청킹 모드에 따라 원본 본문을 분할한다."""

    text = chunk.body

    # 원본 유지 모드
    if config.mode == ChunkingMode.WHOLE:
        return [text]

    # 고정 크기 청킹
    if config.mode == ChunkingMode.FIXED:
        return split_fixed_text(text, config)

    # 의미 기반 + 고정 크기 청킹
    if config.mode == ChunkingMode.SEMANTIC_FIXED:
        # 짧은 문서는 원본 유지
        if len(text) <= config.max_chunk_chars:
            return [text]

        # 긴 문서의 의미 분석에는 임베딩 함수 필수
        if embed_sentences is None:
            raise ValueError("Semantic Chunking에는 임베딩 함수가 필요합니다.")

        return split_semantic_text(
            text,
            config,
            embed_sentences,
        )

    raise ValueError("지원하지 않는 청킹 모드입니다.")


def build_hybrid_chunks(
    source_chunks: Iterable[RAGChunk],
    config: ChunkingConfig,
    *,
    embed_sentences: EmbeddingFunction | None = None,
) -> list[HybridChunkRecord]:
    """기존 RAGChunk를 Hybrid Chunking 결과로 변환한다.

    보안 원칙:
    - 원본 단위로만 분할한다.
    - 서로 다른 NPC 지식을 합치지 않는다.
    - 기존 policy_id와 character_id를 유지한다.
    - 원본에 없는 관리자 메타데이터를 추가하지 않는다.
    - 실제 접근 허용 여부는 기존 정책 엔진에서 판정한다.
    """

    results: list[HybridChunkRecord] = []

    seen_sources: set[tuple[str, str, str]] = set()
    seen_point_ids: set[UUID] = set()

    for source in source_chunks:
        # 1. 입력 타입 검증
        if not isinstance(source, RAGChunk):
            raise TypeError("RAGChunk 타입만 입력할 수 있습니다.")

        # 2. 원본 중복 검사
        source_key = (
            source.case_id,
            source.source_type,
            source.source_id,
        )

        if source_key in seen_sources:
            raise ValueError(f"중복 원본 ID: {source.source_id}")

        seen_sources.add(source_key)

        # 3. 원본 단위 텍스트 분할
        parts = _split_chunk_text(
            source,
            config,
            embed_sentences,
        )

        if not parts:
            raise ValueError("청킹 결과가 비어 있습니다.")

        total = len(parts)

        # 4. 하위 청크 생성
        for index, part in enumerate(parts):
            if not part.strip():
                raise ValueError("비어 있는 하위 청크가 생성되었습니다.")

            # 분할되지 않은 원본은 UUID와 텍스트 유지
            if total == 1:
                chunk = source

            else:
                # 첫 번째 하위 청크는 원본 UUID 사용
                if index == 0:
                    new_point_id = source.chunk_id

                else:
                    # 동일한 원본과 순서는 항상 동일한 UUID
                    new_point_id = uuid5(
                        source.chunk_id,
                        f"rag-chunk:{index}",
                    )

                # 기존 메타데이터를 검증하며 재생성
                payload = source.model_dump()

                payload.update(
                    {
                        "chunk_id": new_point_id,
                        "body": part,
                        "search_text": part,
                    }
                )

                chunk = RAGChunk.model_validate(payload)

            # 5. 전체 Point ID 중복 차단
            if chunk.chunk_id in seen_point_ids:
                raise ValueError(f"중복 Chunk UUID: {chunk.chunk_id}")

            seen_point_ids.add(chunk.chunk_id)

            # 6. 청크 순서 및 원본 UUID 보존
            results.append(
                HybridChunkRecord(
                    chunk=chunk,
                    parent_point_id=source.chunk_id,
                    chunk_index=index,
                    chunk_count=total,
                )
            )

    if not results:
        raise ValueError("청킹 대상 데이터가 없습니다.")

    return results
