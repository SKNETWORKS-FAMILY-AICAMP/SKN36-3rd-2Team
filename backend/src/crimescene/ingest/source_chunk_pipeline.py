"""원본 문서 로딩 결과를 Hybrid Chunking에 연결한다."""

from collections.abc import Collection, Iterable

from crimescene.ingest.chunking_config import ChunkingConfig
from crimescene.ingest.hybrid_chunker import (
    HybridChunkRecord,
    build_hybrid_chunks,
)
from crimescene.ingest.player_document_chunker import (
    build_player_document_chunks,
)
from crimescene.ingest.semantic_chunker import EmbeddingFunction
from crimescene.ingest.source_loader import LoadedSourceDocument
from crimescene.scenario.schemas.document import PlayerDocument


def build_player_source_chunks(
    bindings: Iterable[tuple[LoadedSourceDocument, PlayerDocument]],
    *,
    expected_case_id: str,
    valid_policy_ids: Collection[str],
    config: ChunkingConfig,
    embed_sentences: EmbeddingFunction | None = None,
) -> list[HybridChunkRecord]:
    """검증된 원본 메타데이터를 이용해 Hybrid 청크를 생성한다.

    bindings:
        (추출한 원본 문서, 신뢰할 수 있는 PlayerDocument)

    주의:
        PlayerDocument의 정책과 메타데이터는 서버가
        관리하는 신뢰 데이터에서 가져와야 한다.
    """

    documents: list[PlayerDocument] = []

    seen_document_ids: set[str] = set()

    seen_sources: set[tuple[str, int | None]] = set()

    # 1. 로딩된 문서와 원본 메타데이터 검증
    for source, document in bindings:
        if not isinstance(source, LoadedSourceDocument):
            raise TypeError("LoadedSourceDocument 타입이 필요합니다.")

        if not isinstance(document, PlayerDocument):
            raise TypeError("PlayerDocument 타입이 필요합니다.")

        # 2. 문서 본문이 일치하는지 확인
        if source.body != document.body:
            raise ValueError("원본 파일과 등록된 문서 본문이 일치하지 않습니다.")

        # 3. 사건 ID 확인
        if document.case_id != expected_case_id:
            raise ValueError("다른 사건의 문서를 등록할 수 없습니다.")

        # 4. 접근 정책 등록 여부 확인
        if document.policy_id not in valid_policy_ids:
            raise ValueError("등록되지 않은 접근 정책입니다.")

        # 5. 원본 파일 중복 등록 방지
        source_key = (
            source.source_name,
            source.record_number,
        )

        if source_key in seen_sources:
            raise ValueError("중복된 원본 파일 레코드입니다.")

        seen_sources.add(source_key)

        # 6. 문서 ID 중복 확인
        if document.doc_id in seen_document_ids:
            raise ValueError("중복된 문서 ID입니다.")

        seen_document_ids.add(document.doc_id)

        documents.append(document)

    # 7. 빈 입력 차단
    if not documents:
        raise ValueError("청킹할 문서가 없습니다.")

    # 8. 기존 PlayerDocument 청킹 엔진 재사용
    source_chunks = build_player_document_chunks(
        documents,
        expected_case_id=expected_case_id,
        valid_policy_ids=valid_policy_ids,
    )

    # 9. Fixed / Semantic / Hybrid Chunking 연결
    return build_hybrid_chunks(
        source_chunks,
        config,
        embed_sentences=embed_sentences,
    )
