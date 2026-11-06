from crimescene.ingest.chunking_config import ChunkingConfig


def split_fixed_text(
    text: str,
    config: ChunkingConfig,
) -> list[str]:
    """문자 수 기준으로 텍스트를 분할한다.

    특징:
    - 최대 청크 크기 준수
    - Overlap 적용
    - 짧은 문서는 원본 유지
    - 마지막 청크가 너무 짧으면 가능한 범위에서 경계 조정
    - 원본 텍스트 순서 및 내용 보존

    주의:
    이 함수는 순수 텍스트 분할 함수이다.
    접근 권한 검사와 청크 ID 생성은 상위 계층에서 처리한다.
    """

    # 1. 입력 데이터 타입 검증
    if not isinstance(text, str):
        raise TypeError("청킹 대상은 문자열이어야 합니다.")

    # 2. 빈 문자열 및 공백만 있는 문자열 차단
    if not text.strip():
        raise ValueError("청킹할 텍스트가 비어 있습니다.")

    max_chars = config.max_chunk_chars
    min_chars = config.min_chunk_chars
    overlap = config.overlap_chars

    text_length = len(text)

    # 3. 짧은 문서는 분할하지 않는다.
    if text_length <= max_chars:
        return [text]

    chunks: list[str] = []

    start = 0

    # 4. 고정 크기 청킹
    while start < text_length:
        end = min(
            start + max_chars,
            text_length,
        )

        # 5. 마지막 청크가 너무 짧아지는 경우
        # 가능한 범위에서 현재 청크 경계를 조정한다.
        if end < text_length:
            next_start = end - overlap
            remaining_chars = text_length - next_start

            if remaining_chars < min_chars:
                adjusted_end = text_length - min_chars + overlap

                # 조정 후 현재 청크도 최소 길이를
                # 충족하고, 다음 시작점이 앞으로
                # 진행하는 경우에만 경계를 변경한다.
                if (
                    start + min_chars <= adjusted_end < end
                    and adjusted_end - overlap > start
                ):
                    end = adjusted_end

        # 6. 원본 문자열을 그대로 분할한다.
        chunk = text[start:end]

        chunks.append(chunk)

        # 7. 마지막 청크면 종료
        if end == text_length:
            break

        # 8. Overlap 적용
        start = end - overlap

    return chunks
