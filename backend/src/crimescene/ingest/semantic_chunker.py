import math
import re
from collections.abc import Callable, Sequence

from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)
from crimescene.ingest.fixed_chunker import split_fixed_text

# 문장 목록을 입력받아 각 문장의 임베딩을 반환하는 함수
EmbeddingFunction = Callable[
    [list[str]],
    Sequence[Sequence[float]],
]


# 한국어·영어 문장부호 및 줄바꿈 기준
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])(?=\s)|(?<=\n)(?=\S)")


def split_sentence_units(text: str) -> list[str]:
    """문장 경계에서 텍스트를 분리한다.

    문장부호와 공백을 삭제하지 않으며,
    분리된 단위를 연결하면 원본이 복원된다.
    """

    parts = SENTENCE_BOUNDARY.split(text)

    units: list[str] = []
    pending = ""

    for part in parts:
        if not part:
            continue

        if part.strip():
            units.append(pending + part)
            pending = ""

        elif units:
            units[-1] += part

        else:
            pending += part

    if pending and units:
        units[-1] += pending

    return units


def normalize_embedding(
    embedding: Sequence[float],
) -> tuple[float, ...]:
    """임베딩을 단위 벡터로 정규화한다."""

    try:
        vector = tuple(float(value) for value in embedding)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("유효하지 않은 임베딩 값입니다.") from exc

    if not vector:
        raise ValueError("빈 임베딩 벡터입니다.")

    if not all(math.isfinite(value) for value in vector):
        raise ValueError("임베딩에 유한하지 않은 값이 있습니다.")

    norm = math.sqrt(sum(value * value for value in vector))

    if not math.isfinite(norm) or norm == 0:
        raise ValueError("정규화할 수 없는 임베딩입니다.")

    return tuple(value / norm for value in vector)


def cosine_similarity(
    vector_a: Sequence[float],
    vector_b: Sequence[float],
) -> float:
    """두 임베딩 사이의 코사인 유사도를 계산한다."""

    if len(vector_a) != len(vector_b):
        raise ValueError("임베딩 차원이 일치하지 않습니다.")

    normalized_a = normalize_embedding(vector_a)
    normalized_b = normalize_embedding(vector_b)

    similarity = math.sumprod(
        normalized_a,
        normalized_b,
    )

    return max(-1.0, min(1.0, similarity))


def split_semantic_text(
    text: str,
    config: ChunkingConfig,
    embed_sentences: EmbeddingFunction,
) -> list[str]:
    """의미 기반 청킹과 고정 크기 청킹을 결합한다.

    1. 문장을 분리한다.
    2. 문장 임베딩을 생성한다.
    3. 인접 문장 간 의미 유사도를 계산한다.
    4. 유사도가 낮은 지점에서 분할한다.
    5. 긴 청크는 Fixed-size Chunker로 추가 분할한다.

    원본 문서 하나씩 호출해야 하며,
    서로 다른 접근 정책의 문서를 합치지 않는다.
    """

    if not isinstance(text, str):
        raise TypeError("청킹 대상은 문자열이어야 합니다.")

    if not text.strip():
        raise ValueError("청킹할 텍스트가 비어 있습니다.")

    if config.mode != ChunkingMode.SEMANTIC_FIXED:
        raise ValueError("Semantic Chunker에는 semantic_fixed 모드가 필요합니다.")

    # 짧은 문서는 분할하지 않는다.
    if len(text) <= config.max_chunk_chars:
        return [text]

    # 1. 문장 분리
    units = split_sentence_units(text)

    # 문장 경계를 찾지 못했다면 Fixed-size 적용
    if len(units) <= 1:
        return split_fixed_text(text, config)

    # 2. 문장 임베딩 생성
    embeddings = list(embed_sentences([unit.strip() for unit in units]))

    if len(embeddings) != len(units):
        raise ValueError("문장 수와 임베딩 수가 일치하지 않습니다.")

    # 3. 임베딩 검증
    normalized = [normalize_embedding(embedding) for embedding in embeddings]

    dimensions = {len(vector) for vector in normalized}

    if len(dimensions) != 1:
        raise ValueError("임베딩 차원이 일치하지 않습니다.")

    # 4. 의미 유사도 기반 그룹 생성
    semantic_groups: list[str] = []

    current_group = units[0]

    for index in range(1, len(units)):
        similarity = math.sumprod(
            normalized[index - 1],
            normalized[index],
        )

        if similarity < config.semantic_similarity_threshold:
            semantic_groups.append(current_group)
            current_group = units[index]

        else:
            current_group += units[index]

    semantic_groups.append(current_group)

    # 5. 최대 크기를 초과하는 그룹에 Fixed-size 적용
    chunks: list[str] = []

    for group in semantic_groups:
        if len(group) > config.max_chunk_chars:
            chunks.extend(split_fixed_text(group, config))
        else:
            chunks.append(group)

    return chunks
