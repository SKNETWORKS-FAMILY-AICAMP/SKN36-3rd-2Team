"""OllamaEmbedder 단위 테스트."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ollama import Client

from crimescene.ingest.ollama_embedder import OllamaEmbedder

VECTOR_SIZE = 1024


@pytest.fixture
def mock_client():
    """실제 Ollama를 호출하지 않는 테스트 클라이언트."""

    client = Mock(spec=Client)

    def fake_embed(*, model, input, truncate):
        assert model
        assert truncate is False

        return SimpleNamespace(
            embeddings=[
                [float(index + 1)] * VECTOR_SIZE for index, _ in enumerate(input)
            ]
        )

    client.embed.side_effect = fake_embed

    return client


def test_default_configuration(mock_client):
    """기본 모델 및 벡터 설정 확인."""

    embedder = OllamaEmbedder(client=mock_client)

    assert embedder.model == "bge-m3"
    assert embedder.vector_size == 1024
    assert embedder.batch_size == 16


def test_korean_query_embedding(mock_client):
    """한국어 질문을 1024차원으로 변환."""

    embedder = OllamaEmbedder(client=mock_client)

    vector = embedder.embed_query("신기범은 사건 당일 누구를 만났나요?")

    assert len(vector) == 1024
    assert all(isinstance(value, float) for value in vector)


def test_multiple_text_embeddings(mock_client):
    """여러 문장에 대응하는 벡터 생성."""

    embedder = OllamaEmbedder(client=mock_client)

    vectors = embedder.embed_texts(
        [
            "사건 당일의 출입 기록",
            "목격자의 진술",
        ]
    )

    assert len(vectors) == 2
    assert all(len(vector) == 1024 for vector in vectors)
    assert vectors[0] != vectors[1]


def test_batch_processing(mock_client):
    """Batch 크기에 따라 요청을 나눈다."""

    embedder = OllamaEmbedder(
        client=mock_client,
        batch_size=2,
    )

    vectors = embedder.embed_texts(
        [
            "첫 번째 문장",
            "두 번째 문장",
            "세 번째 문장",
            "네 번째 문장",
            "다섯 번째 문장",
        ]
    )

    assert len(vectors) == 5
    assert mock_client.embed.call_count == 3

    batch_sizes = [
        len(call.kwargs["input"]) for call in mock_client.embed.call_args_list
    ]

    assert batch_sizes == [2, 2, 1]


def test_model_name_forwarded(mock_client):
    """설정한 모델명이 Ollama에 전달되는지 확인."""

    embedder = OllamaEmbedder(
        model="bge-m3",
        client=mock_client,
    )

    embedder.embed_query("테스트 질문")

    mock_client.embed.assert_called_once_with(
        model="bge-m3",
        input=["테스트 질문"],
        truncate=False,
    )


def test_semantic_chunker_callback(mock_client):
    """기존 Semantic Chunker의 임베딩 함수와 호환."""

    embedder = OllamaEmbedder(client=mock_client)

    vectors = embedder(
        [
            "사건 발생 전 상황",
            "사건 발생 후 상황",
        ]
    )

    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


@pytest.mark.parametrize(
    ("texts", "expected_error"),
    [
        ("문자열 하나", TypeError),
        (None, TypeError),
        (123, TypeError),
        ([], ValueError),
        ([""], ValueError),
        (["   "], ValueError),
        (["정상 문장", 123], TypeError),
    ],
)
def test_invalid_inputs_rejected(
    mock_client,
    texts,
    expected_error,
):
    """잘못된 입력은 Ollama 호출 전에 차단."""

    embedder = OllamaEmbedder(client=mock_client)

    with pytest.raises(expected_error):
        embedder.embed_texts(texts)

    mock_client.embed.assert_not_called()


@pytest.mark.parametrize(
    "model",
    ["", "   "],
)
def test_empty_model_rejected(mock_client, model):
    """빈 모델 이름 차단."""

    with pytest.raises(ValueError):
        OllamaEmbedder(
            model=model,
            client=mock_client,
        )


def test_invalid_model_type_rejected(mock_client):
    """문자열이 아닌 모델 이름 차단."""

    with pytest.raises(TypeError):
        OllamaEmbedder(
            model=123,
            client=mock_client,
        )


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("vector_size", 0),
        ("vector_size", -1),
        ("batch_size", 0),
        ("batch_size", -1),
    ],
)
def test_invalid_configuration_rejected(
    mock_client,
    parameter,
    value,
):
    """잘못된 벡터 차원 및 Batch 크기 차단."""

    with pytest.raises(ValueError):
        OllamaEmbedder(
            client=mock_client,
            **{parameter: value},
        )


def test_embedding_count_mismatch_rejected(mock_client):
    """입력 개수와 출력 벡터 개수가 다르면 거부."""

    mock_client.embed.side_effect = None
    mock_client.embed.return_value = SimpleNamespace(embeddings=[[0.1] * VECTOR_SIZE])

    embedder = OllamaEmbedder(client=mock_client)

    with pytest.raises(
        ValueError,
        match="임베딩 수가 일치하지 않습니다",
    ):
        embedder.embed_texts(["첫 번째 문장", "두 번째 문장"])


def test_embedding_dimension_mismatch_rejected(mock_client):
    """1024차원이 아닌 벡터는 거부."""

    mock_client.embed.side_effect = None
    mock_client.embed.return_value = SimpleNamespace(embeddings=[[0.1] * 512])

    embedder = OllamaEmbedder(client=mock_client)

    with pytest.raises(
        ValueError,
        match="벡터 차원이 일치하지 않습니다",
    ):
        embedder.embed_query("테스트 질문")


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_vectors_rejected(
    mock_client,
    invalid_value,
):
    """NaN 및 무한대 벡터 차단."""

    mock_client.embed.side_effect = None
    mock_client.embed.return_value = SimpleNamespace(
        embeddings=[[invalid_value] * VECTOR_SIZE]
    )

    embedder = OllamaEmbedder(client=mock_client)

    with pytest.raises(
        ValueError,
        match="유효하지 않은 임베딩 값",
    ):
        embedder.embed_query("테스트 질문")


def test_zero_vector_rejected(mock_client):
    """모든 값이 0인 벡터 차단."""

    mock_client.embed.side_effect = None
    mock_client.embed.return_value = SimpleNamespace(embeddings=[[0.0] * VECTOR_SIZE])

    embedder = OllamaEmbedder(client=mock_client)

    with pytest.raises(
        ValueError,
        match="영벡터",
    ):
        embedder.embed_query("테스트 질문")
