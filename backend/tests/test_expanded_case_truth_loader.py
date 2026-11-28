
"""이슈 #230 - 확장판 판정 원장 로더 보안 검증."""

import hashlib
import json

import pytest

from crimescene.scenario.expanded_ending import (
    ExpandedCaseTruth,
)

from crimescene.scenario.loaders.expanded_case_truth_loader import (
    MAX_TRUTH_FILE_SIZE,
    load_expanded_case_truth,
)


def checksum(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def write_raw(tmp_path, raw):
    path = tmp_path / "synthetic-truth.json"
    path.write_bytes(raw)

    return path, checksum(raw)


def write_truth(tmp_path, payload):
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    return write_raw(tmp_path, raw)


@pytest.fixture
def synthetic_truth():
    """실제 사건 정본과 무관한 테스트 전용 원장."""

    return {
        "case_id": "CASE-001",
        "content_version": "case001_1120",
        "access_scope": "ENGINE_ONLY",
        "perpetrator_character_id": "C02",
        "motive": "TEST ONLY MOTIVE",
        "cause_of_death": "TEST ONLY CAUSE",
        "crime_method": "TEST ONLY METHOD",
        "crime_event_id": "TEST ONLY EVENT",
        "proof_axes": [
            {
                "axis": "motive",
                "evidence_options": [["E01", "E02"]],
            },
            {
                "axis": "access",
                "evidence_options": [["E03", "E04"]],
            },
            {
                "axis": "timeline",
                "evidence_options": [["E05", "E06"]],
            },
            {
                "axis": "coverup",
                "evidence_options": [["E08", "E09"]],
            },
        ],
    }


def test_load_expanded_truth_success(
    tmp_path,
    synthetic_truth,
):
    path, digest = write_truth(
        tmp_path,
        synthetic_truth,
    )

    truth = load_expanded_case_truth(
        path,
        expected_sha256=digest,
    )

    assert isinstance(truth, ExpandedCaseTruth)

    assert truth.case_id == "CASE-001"
    assert truth.content_version == "case001_1120"
    assert truth.access_scope == "ENGINE_ONLY"

    assert len(truth.proof_axes) == 4

    assert {
        item.axis for item in truth.proof_axes
    } == {
        "motive",
        "access",
        "timeline",
        "coverup",
    }


def test_missing_truth_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_expanded_case_truth(
            tmp_path / "missing.json",
            expected_sha256="sha256:" + "0" * 64,
        )


def test_truth_checksum_mismatch(
    tmp_path,
    synthetic_truth,
):
    path, digest = write_truth(
        tmp_path,
        synthetic_truth,
    )

    # 승인 이후 파일이 변경된 상황을 재현한다.
    path.write_bytes(
        path.read_bytes() + b" "
    )

    with pytest.raises(
        PermissionError,
        match="checksum mismatch",
    ):
        load_expanded_case_truth(
            path,
            expected_sha256=digest,
        )


def test_invalid_approved_checksum(
    tmp_path,
    synthetic_truth,
):
    path, _ = write_truth(
        tmp_path,
        synthetic_truth,
    )

    with pytest.raises(
        ValueError,
        match="Invalid approved truth checksum",
    ):
        load_expanded_case_truth(
            path,
            expected_sha256="unverified",
        )


@pytest.mark.parametrize(
    "mode",
    [
        "missing_version",
        "legacy_version",
        "wrong_case",
        "missing_scope",
        "wrong_scope",
        "unknown_npc",
        "blank_motive",
        "missing_axis",
        "protected_evidence",
    ],
)
def test_invalid_truth_schema(
    tmp_path,
    synthetic_truth,
    mode,
):
    if mode == "missing_version":
        synthetic_truth.pop("content_version")

    elif mode == "legacy_version":
        synthetic_truth["content_version"] = "case001_v7_1"

    elif mode == "wrong_case":
        synthetic_truth["case_id"] = "CASE-999"

    elif mode == "missing_scope":
        synthetic_truth.pop("access_scope")

    elif mode == "wrong_scope":
        synthetic_truth["access_scope"] = "PUBLIC"

    elif mode == "unknown_npc":
        synthetic_truth["perpetrator_character_id"] = "C99"

    elif mode == "blank_motive":
        synthetic_truth["motive"] = "   "

    elif mode == "missing_axis":
        synthetic_truth["proof_axes"].pop()

    elif mode == "protected_evidence":
        synthetic_truth["proof_axes"][0][
            "evidence_options"
        ] = [["E01", "E30"]]

    path, digest = write_truth(
        tmp_path,
        synthetic_truth,
    )

    with pytest.raises(
        ValueError,
        match="Invalid expanded private truth",
    ) as error:
        load_expanded_case_truth(
            path,
            expected_sha256=digest,
        )

    # 오류 응답에 비공개 정답 본문이 포함되지 않는다.
    assert "TEST ONLY" not in str(error.value)


def test_malformed_truth_json(tmp_path):
    path, digest = write_raw(
        tmp_path,
        b'{"invalid":',
    )

    with pytest.raises(
        ValueError,
        match="Invalid expanded private truth",
    ):
        load_expanded_case_truth(
            path,
            expected_sha256=digest,
        )


def test_duplicate_truth_json_keys(
    tmp_path,
    synthetic_truth,
):
    raw = json.dumps(
        synthetic_truth
    ).encode("utf-8")

    raw = (
        b'{"case_id":"CASE-001",'
        + raw[1:]
    )

    path, digest = write_raw(
        tmp_path,
        raw,
    )

    with pytest.raises(
        ValueError,
        match="Invalid expanded private truth",
    ):
        load_expanded_case_truth(
            path,
            expected_sha256=digest,
        )


def test_oversized_truth_file(tmp_path):
    path, digest = write_raw(
        tmp_path,
        b"x" * (MAX_TRUTH_FILE_SIZE + 1),
    )

    with pytest.raises(
        ValueError,
        match="Expanded truth file too large",
    ):
        load_expanded_case_truth(
            path,
            expected_sha256=digest,
        )
