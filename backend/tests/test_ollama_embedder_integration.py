"""실제 Ollama BGE-M3 임베딩 통합 테스트."""

import math
import os

import pytest

from crimescene.ingest.ollama_embedder import OllamaEmbedder

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_INTEGRATION") != "1",
    reason="실제 Ollama 통합 테스트는 명시적으로 실행해야 합니다.",
)


def test_real_bge_m3_query_embedding():
    """실제 BGE-M3로 한국어 질문을 임베딩한다."""

    embedder = OllamaEmbedder()

    vector = embedder.embed_query(
        "신기범이 사건 당일 마지막으로 만난 사람은 누구인가요?"
    )

    assert len(vector) == 1024
    assert all(math.isfinite(value) for value in vector)
    assert any(value != 0 for value in vector)


def test_real_bge_m3_batch_embedding():
    """여러 한국어 문장을 Batch로 임베딩한다."""

    embedder = OllamaEmbedder(batch_size=2)

    sentences = [
        "사건 당일 학교 출입 기록",
        "목격자가 남긴 진술",
        "인물 간 갈등 관계",
    ]

    vectors = embedder.embed_texts(sentences)

    assert len(vectors) == 3

    assert all(len(vector) == 1024 for vector in vectors)

    assert all(all(math.isfinite(value) for value in vector) for vector in vectors)

    assert vectors[0] != vectors[1]
    assert vectors[1] != vectors[2]


def test_real_bge_m3_semantic_callback():
    """기존 Semantic Chunker용 콜백 인터페이스 확인."""

    embedder = OllamaEmbedder()

    sentences = [
        "신기범은 사건 당시 학교에 있었습니다.",
        "사건 당일의 출입 기록을 조사했습니다.",
    ]

    vectors = embedder(sentences)

    assert len(vectors) == len(sentences)
    assert all(len(vector) == 1024 for vector in vectors)
