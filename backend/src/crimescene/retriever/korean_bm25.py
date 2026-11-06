"""Kiwi 기반 한국어 BM25 Sparse Vector Encoder."""

import hashlib
import math
from collections import Counter
from collections.abc import Sequence

from kiwipiepy import Kiwi
from qdrant_client import models

DEFAULT_K1 = 1.2
DEFAULT_B = 0.75

# 검색에 사용할 품사
SEARCH_TAGS = {
    "VV",  # 동사
    "VA",  # 형용사
    "VX",  # 보조 용언
    "XR",  # 어근
    "SL",  # 영문
    "SN",  # 숫자
}

# 빈도가 높지만 검색 의미가 낮은 일부 용언
STOPWORDS = {
    "하",
    "되",
}


class KoreanBM25Encoder:
    """한국어 텍스트를 BM25 Sparse Vector로 변환한다."""

    def __init__(
        self,
        *,
        k1: float = DEFAULT_K1,
        b: float = DEFAULT_B,
        kiwi: Kiwi | None = None,
    ) -> None:
        if (
            isinstance(k1, bool)
            or not isinstance(k1, (int, float))
            or not math.isfinite(k1)
            or k1 <= 0
        ):
            raise ValueError("k1은 양의 유한한 숫자여야 합니다.")

        if (
            isinstance(b, bool)
            or not isinstance(b, (int, float))
            or not math.isfinite(b)
            or not 0 <= b <= 1
        ):
            raise ValueError("b는 0~1 사이의 숫자여야 합니다.")

        self.k1 = float(k1)
        self.b = float(b)

        self.kiwi = kiwi if kiwi is not None else Kiwi()

        self.avg_document_length: float | None = None

    def tokenize(self, text: str) -> list[str]:
        """검색에 사용할 한국어 키워드를 추출한다."""

        if not isinstance(text, str):
            raise TypeError("텍스트는 문자열이어야 합니다.")

        if not text.strip():
            raise ValueError("텍스트가 비어 있습니다.")

        tokens = []

        for token in self.kiwi.tokenize(text):
            tag = token.tag
            word = token.form.casefold().strip()

            # 명사 또는 검색에 유용한 품사만 사용
            if not (tag.startswith("NN") or tag in SEARCH_TAGS):
                continue

            if not word or word in STOPWORDS:
                continue

            tokens.append(word)

        if not tokens:
            raise ValueError("검색에 사용할 키워드를 추출하지 못했습니다.")

        return tokens

    @staticmethod
    def token_id(token: str) -> int:
        """키워드를 재현 가능한 32비트 정수 ID로 변환한다.

        Python 내장 hash()는 실행마다 달라질 수 있으므로
        사용하지 않는다.
        """

        digest = hashlib.blake2b(
            token.encode("utf-8"),
            digest_size=4,
        ).digest()

        return int.from_bytes(
            digest,
            byteorder="little",
            signed=False,
        )

    def _count_token_ids(
        self,
        tokens: list[str],
    ) -> Counter[int]:
        """키워드별 출현 횟수를 계산한다."""

        counts: Counter[int] = Counter()
        seen_ids: dict[int, str] = {}

        for token in tokens:
            index = self.token_id(token)

            # 같은 문서 내부의 해시 충돌 차단
            previous = seen_ids.get(index)

            if previous is not None and previous != token:
                raise ValueError("서로 다른 키워드의 Sparse ID가 충돌했습니다.")

            seen_ids[index] = token
            counts[index] += 1

        return counts

    def fit(self, documents: Sequence[str]) -> None:
        """전체 문서 집합을 기준으로 평균 길이를 계산한다.

        반드시 전체 코퍼스로 실행해야 한다.
        Batch마다 개별적으로 fit하면 BM25 점수가 달라진다.
        """

        if isinstance(documents, (str, bytes)):
            raise TypeError("문서 목록을 전달해야 합니다.")

        if not isinstance(documents, Sequence):
            raise TypeError("문서 목록 타입이 올바르지 않습니다.")

        if not documents:
            raise ValueError("학습할 문서가 없습니다.")

        lengths = [len(self.tokenize(text)) for text in documents]

        self.avg_document_length = sum(lengths) / len(lengths)

    def encode_document(
        self,
        text: str,
    ) -> models.SparseVector:
        """문서를 BM25 가중치가 적용된 Sparse Vector로 변환한다."""

        if self.avg_document_length is None:
            raise RuntimeError("문서 인코딩 전에 fit()이 필요합니다.")

        tokens = self.tokenize(text)

        document_length = len(tokens)

        counts = self._count_token_ids(tokens)

        # BM25 길이 정규화
        normalization = self.k1 * (
            1 - self.b + self.b * (document_length / self.avg_document_length)
        )

        indices = []
        values = []

        for index, tf in sorted(counts.items()):
            # IDF는 Qdrant에서 계산
            weight = tf * (self.k1 + 1) / (tf + normalization)

            indices.append(index)
            values.append(float(weight))

        return models.SparseVector(
            indices=indices,
            values=values,
        )

    def encode_documents(
        self,
        documents: Sequence[str],
    ) -> list[models.SparseVector]:
        """전체 문서 집합을 기준으로 BM25 벡터를 생성한다."""

        # 전체 코퍼스로 평균 길이를 먼저 계산
        self.fit(documents)

        return [self.encode_document(text) for text in documents]

    def encode_query(
        self,
        query: str,
    ) -> models.SparseVector:
        """검색 질문을 Sparse Vector로 변환한다.

        BM25 질문 벡터에는 각 키워드 가중치 1.0을 사용한다.
        """

        tokens = self.tokenize(query)

        counts = self._count_token_ids(tokens)

        indices = sorted(counts)

        return models.SparseVector(
            indices=indices,
            values=[1.0] * len(indices),
        )
