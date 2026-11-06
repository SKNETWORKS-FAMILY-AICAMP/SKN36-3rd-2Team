from collections.abc import Collection, Iterable

from crimescene.ingest.chunk_models import RAGChunk
from crimescene.scenario.schemas.document import PlayerDocument


def build_player_document_chunks(
    documents: Iterable[PlayerDocument],
    *,
    expected_case_id: str,
    valid_policy_ids: Collection[str],
) -> list[RAGChunk]:
    """플레이어 문서를 RAG 청크로 변환한다.

    문서 1개를 청크 1개로 유지한다.

    접근 정책이 없거나 데이터 무결성 검증에 실패하면
    전체 청킹을 중단한다.

    이 함수는 접근 권한을 승인하지 않는다.
    실제 검색 시 GameState 기반 권한 검사가 필요하다.
    """

    if not expected_case_id or not expected_case_id.strip():
        raise ValueError("유효한 사건 ID가 필요합니다.")

    if not valid_policy_ids:
        raise ValueError("접근 정책 목록이 비어 있습니다.")

    chunks: list[RAGChunk] = []

    seen_source_ids: set[str] = set()
    seen_point_ids: set[str] = set()

    for document in documents:
        # 1. 플레이어 문서만 허용
        if not isinstance(document, PlayerDocument):
            raise TypeError("PlayerDocument 타입만 청킹할 수 있습니다.")

        # 2. 사건 ID 검사
        if document.case_id != expected_case_id:
            raise ValueError(f"사건 ID 불일치: {document.doc_id}")

        # 3. 접근 정책 존재 여부 검사
        if document.policy_id not in valid_policy_ids:
            raise ValueError(f"등록되지 않은 접근 정책: {document.policy_id}")

        # 4. 원본 문서 ID 중복 검사
        if document.doc_id in seen_source_ids:
            raise ValueError(f"중복 문서 ID: {document.doc_id}")

        # 5. 허용된 필드만 추출하여 청크 생성
        chunk = RAGChunk(
            chunk_id=document.point_id,
            source_id=document.doc_id,
            source_type="player_document",
            case_id=document.case_id,
            policy_id=document.policy_id,
            family=document.family,
            access_scope=document.access_scope,
            character_id=None,
            incident_year=document.incident_year,
            content_hash=document.content_hash,
            search_text=document.search_text,
            body=document.body,
        )

        # 6. Point ID 중복 검사
        if chunk.point_id in seen_point_ids:
            raise ValueError(f"중복 Point ID: {chunk.point_id}")

        seen_source_ids.add(document.doc_id)
        seen_point_ids.add(chunk.point_id)

        chunks.append(chunk)

    # 7. 빈 데이터 차단
    if not chunks:
        raise ValueError("청킹 대상 플레이어 문서가 없습니다.")

    return chunks
