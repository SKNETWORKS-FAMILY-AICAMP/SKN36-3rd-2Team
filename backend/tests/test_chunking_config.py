import pytest
from pydantic import ValidationError

from crimescene.ingest.chunking_config import (
    ChunkingConfig,
    ChunkingMode,
)


def test_default_chunking_config():
    """기본 청킹 설정 검증."""

    config = ChunkingConfig()

    assert config.mode == ChunkingMode.SEMANTIC_FIXED
    assert config.min_chunk_chars == 120
    assert config.max_chunk_chars == 800
    assert config.overlap_chars == 80
    assert config.semantic_similarity_threshold == 0.65


@pytest.mark.parametrize(
    "mode",
    [
        ChunkingMode.WHOLE,
        ChunkingMode.FIXED,
        ChunkingMode.SEMANTIC_FIXED,
    ],
)
def test_valid_chunking_modes(mode: ChunkingMode):
    """지원하는 청킹 모드 3개 검증."""

    config = ChunkingConfig(mode=mode)

    assert config.mode == mode


def test_custom_chunking_config():
    """사용자 지정 설정 검증."""

    config = ChunkingConfig(
        mode=ChunkingMode.FIXED,
        min_chunk_chars=100,
        max_chunk_chars=500,
        overlap_chars=50,
        semantic_similarity_threshold=0.75,
    )

    assert config.mode == ChunkingMode.FIXED
    assert config.min_chunk_chars == 100
    assert config.max_chunk_chars == 500
    assert config.overlap_chars == 50
    assert config.semantic_similarity_threshold == 0.75


def test_invalid_chunking_mode():
    """지원하지 않는 청킹 모드 차단."""

    with pytest.raises(ValidationError):
        ChunkingConfig(mode="unknown_mode")


def test_invalid_min_chunk_chars():
    """최소 청크 크기가 0이면 차단."""

    with pytest.raises(ValidationError):
        ChunkingConfig(min_chunk_chars=0)


def test_invalid_max_chunk_chars():
    """최대 청크 크기가 너무 작으면 차단."""

    with pytest.raises(ValidationError):
        ChunkingConfig(max_chunk_chars=1)


def test_min_greater_than_max():
    """최소 청크 크기가 최대보다 크면 차단."""

    with pytest.raises(
        ValidationError,
        match="최소 청크 크기",
    ):
        ChunkingConfig(
            min_chunk_chars=900,
            max_chunk_chars=800,
        )


def test_negative_overlap():
    """음수 Overlap 차단."""

    with pytest.raises(ValidationError):
        ChunkingConfig(overlap_chars=-1)


def test_overlap_equal_to_max():
    """Overlap이 최대 청크 크기와 같으면 차단."""

    with pytest.raises(
        ValidationError,
        match="Overlap",
    ):
        ChunkingConfig(
            max_chunk_chars=500,
            overlap_chars=500,
        )


def test_overlap_greater_than_max():
    """Overlap이 최대 청크 크기를 초과하면 차단."""

    with pytest.raises(
        ValidationError,
        match="Overlap",
    ):
        ChunkingConfig(
            max_chunk_chars=500,
            overlap_chars=600,
        )


def test_zero_overlap_allowed():
    """Overlap 0은 허용."""

    config = ChunkingConfig(overlap_chars=0)

    assert config.overlap_chars == 0


@pytest.mark.parametrize(
    "threshold",
    [0.0, 1.0],
)
def test_valid_similarity_threshold(threshold: float):
    """의미 유사도 임계값의 경계값 검증."""

    config = ChunkingConfig(
        semantic_similarity_threshold=threshold,
    )

    assert config.semantic_similarity_threshold == threshold


@pytest.mark.parametrize(
    "threshold",
    [-0.1, 1.1],
)
def test_invalid_similarity_threshold(threshold: float):
    """0~1 범위를 벗어나는 유사도 값 차단."""

    with pytest.raises(ValidationError):
        ChunkingConfig(
            semantic_similarity_threshold=threshold,
        )


def test_extra_field_rejected():
    """정의되지 않은 설정값 차단."""

    with pytest.raises(ValidationError):
        ChunkingConfig(
            unknown_setting="invalid",
        )


def test_config_is_immutable():
    """생성된 청킹 설정 수정 차단."""

    config = ChunkingConfig()

    with pytest.raises(ValidationError):
        config.max_chunk_chars = 2000
