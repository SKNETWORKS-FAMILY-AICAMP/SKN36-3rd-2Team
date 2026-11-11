"""Ollama 기반 로컬 임베딩 생성 모듈."""

import math
from collections.abc import Sequence

from ollama import Client

DEFAULT_EMBEDDING_MODEL = "bge-m3"
DEFAULT_VECTOR_SIZE = 1024
DEFAULT_BATCH_SIZE = 16


class OllamaEmbedder:
    """BGE-M3 기반 문서 및 질문 임베딩 생성기."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        batch_size: int = DEFAULT_BATCH_SIZE,
        client: Client | None = None,
    ) -> None:
        """임베딩 모델과 배치 설정을 초기화한다."""

        if not isinstance(model, str):
            raise TypeError("모델 이름은 문자열이어야 합니다.")

        if not model.strip():
            raise ValueError("임베딩 모델 이름이 비어 있습니다.")

        if vector_size <= 0:
            raise ValueError("벡터 차원은 양수여야 합니다.")

        if batch_size <= 0:
            raise ValueError("배치 크기는 양수여야 합니다.")

        self.model = model
        self.vector_size = vector_size
        self.batch_size = batch_size

        # 별도 주소를 지정하지 않으면 Ollama 기본 설정 사용
        self.client = client if client is not None else Client()

    def embed_texts(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """문서 청크 또는 문장 목록을 임베딩한다."""

        if isinstance(texts, (str, bytes)):
            raise TypeError("문장 목록을 전달해야 합니다.")

        if not isinstance(texts, Sequence):
            raise TypeError("문장 목록 타입이 올바르지 않습니다.")

        if not texts:
            raise ValueError("임베딩할 문장이 없습니다.")

        # 1. 입력 검증
        for index, text in enumerate(texts):
            if not isinstance(text, str):
                raise TypeError(f"{index}번 문장이 문자열이 아닙니다.")

            if not text.strip():
                raise ValueError(f"{index}번 문장이 비어 있습니다.")

        vectors: list[list[float]] = []

        # 2. Batch 단위 임베딩
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])

            response = self.client.embed(
                model=self.model,
                input=batch,
                truncate=False,
                keep_alive="15m",
            )

            batch_vectors = response.embeddings

            # 3. 입력 개수와 출력 개수 검증
            if len(batch_vectors) != len(batch):
                raise ValueError("입력 문장 수와 임베딩 수가 일치하지 않습니다.")

            # 4. 벡터 검증
            for embedding in batch_vectors:
                vector = [float(value) for value in embedding]

                if len(vector) != self.vector_size:
                    raise ValueError("임베딩 벡터 차원이 일치하지 않습니다.")

                if not all(math.isfinite(value) for value in vector):
                    raise ValueError("유효하지 않은 임베딩 값이 존재합니다.")

                if not any(value != 0 for value in vector):
                    raise ValueError("영벡터는 사용할 수 없습니다.")

                vectors.append(vector)

        return vectors

    def embed_query(self, query: str) -> list[float]:
        """플레이어 질문 하나를 임베딩한다."""

        return self.embed_texts([query])[0]

    def __call__(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """기존 Semantic Chunker와 호환되는 호출 방식."""

        return self.embed_texts(texts)
