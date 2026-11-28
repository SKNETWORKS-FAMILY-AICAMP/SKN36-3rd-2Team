"""Issue #165 - expanded ending API integration tests."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from crimescene.api.app import create_app
from crimescene.scenario.case_truth import CaseTruth
from crimescene.scenario.content_compiler import PROPOSED_SCORES
from crimescene.scenario.expanded_ending import (
    DEEP_FLAGS,
    FINAL_FLAG,
    ExpandedCaseTruth,
    ProofAxis,
)
from crimescene.scenario.schemas.evidence import EvidenceRule
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

SELECTIONS = {
    "motive": ["E17", "E27"],
    "access": ["E21", "E23"],
    "timeline": ["E24", "E25"],
    "coverup": ["E20", "E26"],
}


@pytest.fixture
def runtime(tmp_path):
    repository = SQLiteCase001Repository(
        tmp_path / "ending.sqlite3"
    )

    app = create_app(
        repository,
        session_secret="issue165-ending-" + "x" * 40,
    )

    app.state.content_version = "case001_1120"

    legacy = dict(zip(
        [f"E{i:02d}" for i in range(1, 11)],
        [1, 2, 3, 2, 3, 3, 2, 2, 1, 2],
        strict=True,
    ))

    rules = {
        eid: EvidenceRule(
            name=f"Test {eid}",
            score=score,
            holder="C01",
            prerequisites=[],
            presentation=[],
            q=[],
        )
        for eid, score in {
            **legacy,
            **PROPOSED_SCORES,
        }.items()
    }

    app.state.case_truth = ExpandedCaseTruth(
        case_id="CASE-001",
        content_version="case001_1120",
        perpetrator_character_id="C02",
        motive="TEST MOTIVE",
        cause_of_death="TEST CAUSE",
        crime_method="TEST METHOD",
        crime_event_id="TEST EVENT",
        proof_axes=tuple(
            ProofAxis(
                axis=axis,
                evidence_options=(tuple(ids),),
            )
            for axis, ids in SELECTIONS.items()
        ),
    )

    app.state.dialogue_resources = SimpleNamespace(
        evidence_rules=rules,
    )

    with TestClient(app) as client:
        response = client.post("/api/games")
        assert response.status_code == 201

        sid = response.json()["sessionId"]

        response = client.post(
            f"/api/games/{sid}/prologue/complete"
        )

        assert response.status_code == 200

        yield app, client, repository, sid, rules


def prepare(runtime, *, full=True, deep=False, flags=()):
    _, _, repository, sid, rules = runtime

    before = repository.load_state(sid)

    ids = (
        [eid for eid in rules if eid != "E30"]
        if full else ["E01"]
    )

    if deep:
        ids.append("E30")

    state = GameState.model_validate({
        **before.model_dump(),
        "current_chapter": "CH04",
        "unlocked_chapters": [
            "CH00", "CH01", "CH02", "CH03", "CH04",
        ],
        "unlocked_characters": ["C01", "C02"],
        "evidence": {
            eid: {"stage": "found"}
            for eid in ids
        },
        "score": sum(rules[eid].score for eid in ids),
        "flags": list(flags),
        "revision": before.revision + 1,
    })

    repository.commit_state(
        expected_state=before,
        updated_state=state,
    )


def reconstruct(runtime, selections=None):
    _, client, repository, sid, _ = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/reconstruction",
        json={
            "expectedRevision": state.revision,
            "selections": (
                SELECTIONS if selections is None
                else selections
            ),
        },
    )


def accuse(runtime, suspect="C02"):
    _, client, repository, sid, _ = runtime

    state = repository.load_state(sid)

    return client.post(
        f"/api/games/{sid}/accusations",
        json={
            "expectedRevision": state.revision,
            "suspectId": suspect,
        },
    )


def ending(runtime):
    _, client, _, sid, _ = runtime

    response = client.get(
        f"/api/games/{sid}/ending"
    )

    assert response.status_code == 200

    return response.json()


def test_no_evidence_ending(runtime):
    prepare(runtime, full=False)

    _, client, repository, sid, _ = runtime
    state = repository.load_state(sid)

    response = client.post(
        f"/api/games/{sid}/give-up",
        json={"expectedRevision": state.revision},
    )

    assert response.status_code == 200
    assert ending(runtime)["outcome"] == "NO_EVIDENCE"
    assert ending(runtime)["truth"] is None


def test_unsolved_ending(runtime):
    prepare(runtime)

    for _ in range(3):
        assert accuse(runtime, "C01").status_code == 200

    assert ending(runtime)["outcome"] == "UNSOLVED"
    assert ending(runtime)["truth"] is None


def test_estimated_ending(runtime):
    prepare(runtime)

    assert accuse(runtime).status_code == 200

    result = ending(runtime)

    assert result["outcome"] == "ESTIMATED"
    assert result["truth"] is None
    assert result["deepEligible"] is False


def test_full_ending(runtime):
    prepare(runtime)

    response = reconstruct(runtime)

    assert response.status_code == 200
    assert response.json()["accepted"] is True

    assert accuse(runtime).status_code == 200

    result = ending(runtime)

    assert result["outcome"] == "FULL"
    assert result["truth"]["perpetratorId"] == "C02"


def test_deep_ending(runtime):
    prepare(runtime, deep=True, flags=DEEP_FLAGS)

    assert reconstruct(runtime).status_code == 200
    assert accuse(runtime).status_code == 200

    result = ending(runtime)

    assert result["outcome"] == "DEEP"
    assert result["deepEligible"] is True


def test_deep_without_consent_is_full(runtime):
    prepare(
        runtime,
        deep=True,
        flags=DEEP_FLAGS - {
            "consent_and_safety_verified"
        },
    )

    assert reconstruct(runtime).status_code == 200
    assert accuse(runtime).status_code == 200

    assert ending(runtime)["outcome"] == "FULL"


def test_wrong_reconstruction_not_granted(runtime):
    prepare(runtime)

    wrong = {
        **SELECTIONS,
        "motive": ["E01", "E02"],
    }

    response = reconstruct(runtime, wrong)

    assert response.status_code == 200
    assert response.json()["accepted"] is False

    _, _, repository, sid, _ = runtime

    assert FINAL_FLAG not in repository.load_state(sid).flags


def test_three_independent_axes_sufficient(runtime):
    prepare(runtime)

    selections = {
        key: value
        for key, value in SELECTIONS.items()
        if key != "coverup"
    }

    response = reconstruct(runtime, selections)

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_reconstruction_idempotent(runtime):
    prepare(runtime)

    assert reconstruct(runtime).status_code == 200

    _, _, repository, sid, _ = runtime

    before = repository.load_state(sid)
    response = reconstruct(runtime)

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert repository.load_state(sid) == before


def test_legacy_truth_cannot_finish_expanded_game(runtime):
    prepare(runtime)

    app, _, repository, sid, _ = runtime

    app.state.case_truth = CaseTruth(
        case_id="CASE-001",
        perpetrator_character_id="C01",
        motive="LEGACY SECRET",
        cause_of_death="LEGACY SECRET",
        crime_method="LEGACY SECRET",
        crime_event_id="LEGACY EVENT",
    )

    before = repository.load_state(sid)

    assert accuse(runtime).status_code == 409
    assert repository.load_state(sid) == before


def test_ending_hidden_before_finish(runtime):
    prepare(runtime)

    _, client, _, sid, _ = runtime

    response = client.get(
        f"/api/games/{sid}/ending"
    )

    assert response.status_code == 409


# Issue #191 - protected ending images

@pytest.fixture
def private_ending_images(tmp_path, monkeypatch):
    directory = tmp_path / "private-ending-images"
    directory.mkdir()

    # Synthetic transport fixtures, not actual spoiler images.
    images = {
        name: b"\x89PNG\r\n\x1a\n" + name.encode("ascii")
        for name in (
            "deep_album_blank.png",
            "deep_album_filled.png",
            "escaped.png",
        )
    }

    for name, content in images.items():
        (directory / name).write_bytes(content)

    monkeypatch.setenv(
        "CRIMESCENE_ENDING_IMAGE_DIR",
        str(directory),
    )

    return directory, images


def assert_private_image_headers(response):
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def finish_image_test_game(runtime, code):
    if code == "NO_EVIDENCE":
        prepare(runtime, full=False)

        _, client, repository, sid, _ = runtime

        response = client.post(
            f"/api/games/{sid}/give-up",
            json={
                "expectedRevision":
                    repository.load_state(sid).revision,
            },
        )
        assert response.status_code == 200

    elif code == "UNSOLVED":
        prepare(runtime)

        for _ in range(3):
            assert accuse(runtime, "C01").status_code == 200

    elif code == "ESTIMATED":
        prepare(runtime)
        assert accuse(runtime).status_code == 200

    elif code == "FULL":
        prepare(runtime)
        assert reconstruct(runtime).status_code == 200
        assert accuse(runtime).status_code == 200

    elif code == "DEEP":
        prepare(runtime, deep=True, flags=DEEP_FLAGS)
        assert reconstruct(runtime).status_code == 200
        assert accuse(runtime).status_code == 200

    else:
        raise ValueError("Invalid ending code")

    assert ending(runtime)["outcome"] == code


@pytest.mark.parametrize(
    ("code", "expected_names"),
    [
        ("NO_EVIDENCE", ()),
        ("UNSOLVED", ("escaped.png",)),
        ("ESTIMATED", ()),
        ("FULL", ()),
        ("DEEP", (
            "deep_album_blank.png",
            "deep_album_filled.png",
        )),
    ],
)
def test_protected_images_for_each_ending(
    runtime,
    private_ending_images,
    code,
    expected_names,
):
    _, client, repository, sid, _ = runtime
    _, images = private_ending_images

    finish_image_test_game(runtime, code)

    before = repository.load_state(sid)
    base = f"/api/games/{sid}/ending/images"

    response = client.get(base)

    assert response.status_code == 200
    assert_private_image_headers(response)

    assert response.json() == {
        "endingCode": code,
        "images": [
            {
                "index": index,
                "url": f"{base}/{index}",
            }
            for index in range(1, len(expected_names) + 1)
        ],
    }

    for index, name in enumerate(expected_names, start=1):
        response = client.get(f"{base}/{index}")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == images[name]
        assert_private_image_headers(response)

    for index in (0, -1, len(expected_names) + 1, 999):
        response = client.get(f"{base}/{index}")
        assert response.status_code == 404
        assert_private_image_headers(response)

    # Read-only API must not change the game state.
    assert repository.load_state(sid) == before


def test_protected_images_before_finish(
    runtime,
    private_ending_images,
):
    _, client, repository, sid, _ = runtime

    before = repository.load_state(sid)
    base = f"/api/games/{sid}/ending/images"

    for url in (base, f"{base}/1", f"{base}/2"):
        response = client.get(url)
        assert response.status_code == 409
        assert_private_image_headers(response)

    assert repository.load_state(sid) == before


def test_protected_images_without_ownership(
    runtime,
    private_ending_images,
):
    app, _, _, sid, _ = runtime

    finish_image_test_game(runtime, "DEEP")

    base = f"/api/games/{sid}/ending/images"

    with TestClient(app) as outsider:
        for url in (base, f"{base}/1", f"{base}/2"):
            response = outsider.get(url)
            assert response.status_code == 404
            assert_private_image_headers(response)

        # Ownership of another game does not grant access.
        assert outsider.post("/api/games").status_code == 201

        for url in (base, f"{base}/1"):
            response = outsider.get(url)
            assert response.status_code == 404
            assert_private_image_headers(response)


def test_protected_images_ignore_client_ending_override(
    runtime,
    private_ending_images,
):
    _, client, _, sid, _ = runtime
    _, images = private_ending_images

    finish_image_test_game(runtime, "UNSOLVED")

    base = f"/api/games/{sid}/ending/images"

    response = client.get(
        f"{base}/1",
        params={
            "endingCode": "DEEP",
            "filename": "deep_album_filled.png",
        },
    )

    assert response.status_code == 200
    assert response.content == images["escaped.png"]

    assert client.get(f"{base}/2").status_code == 404


def test_protected_image_missing_file(
    runtime,
    private_ending_images,
):
    _, client, _, sid, _ = runtime
    directory, _ = private_ending_images

    finish_image_test_game(runtime, "DEEP")

    (directory / "deep_album_filled.png").unlink()

    base = f"/api/games/{sid}/ending/images"

    assert client.get(base).status_code == 404
    assert client.get(f"{base}/2").status_code == 404


def test_protected_image_path_escape(
    runtime,
    private_ending_images,
    tmp_path,
):
    _, client, _, sid, _ = runtime
    directory, _ = private_ending_images

    finish_image_test_game(runtime, "DEEP")

    outside = tmp_path / "outside.png"
    outside.write_bytes(b"PRIVATE TEST CONTENT")

    image = directory / "deep_album_blank.png"
    image.unlink()

    try:
        image.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links unavailable on this system")

    response = client.get(
        f"/api/games/{sid}/ending/images/1"
    )

    assert response.status_code == 404
    assert b"PRIVATE TEST CONTENT" not in response.content


@pytest.mark.parametrize("outside_directory", [True, False])
def test_protected_image_resolved_path_denied(
    runtime,
    private_ending_images,
    tmp_path,
    monkeypatch,
    outside_directory,
):
    """Verify resolved-path rejection without symlink privileges."""
    from pathlib import Path

    _, client, _, sid, _ = runtime
    directory, _ = private_ending_images

    finish_image_test_game(runtime, "DEEP")

    directory = directory.resolve()
    candidate = directory / "deep_album_blank.png"

    alternative = (
        tmp_path / "outside.png"
        if outside_directory
        else directory / "deep_album_filled.png"
    ).resolve()

    if outside_directory:
        alternative.write_bytes(b"PRIVATE TEST CONTENT")

    original_resolve = Path.resolve

    def simulated_resolve(self, *args, **kwargs):
        if self == candidate:
            return alternative
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulated_resolve)

    response = client.get(
        f"/api/games/{sid}/ending/images/1"
    )

    assert response.status_code == 404
    assert_private_image_headers(response)
    assert b"PRIVATE TEST CONTENT" not in response.content


@pytest.mark.parametrize(
    ("code", "names"),
    [
        ("DEEP", (
            "deep_album_blank.png",
            "deep_album_filled.png",
        )),
        ("UNSOLVED", ("escaped.png",)),
    ],
)
def test_real_private_ending_image_delivery(
    runtime,
    monkeypatch,
    code,
    names,
):
    """Opt-in verification of privately supplied PNG assets."""
    import os
    import hashlib
    from pathlib import Path

    if os.getenv("RUN_PRIVATE_IMAGE_INTEGRATION") != "1":
        pytest.skip("Private image integration is opt-in")

    directory = (
        Path(__file__).resolve().parents[1]
        / ".local"
        / "case001_ending_images"
    )

    monkeypatch.setenv(
        "CRIMESCENE_ENDING_IMAGE_DIR",
        str(directory),
    )

    _, client, repository, sid, _ = runtime

    finish_image_test_game(runtime, code)

    before = repository.load_state(sid)
    base = f"/api/games/{sid}/ending/images"

    listing = client.get(base)

    assert listing.status_code == 200
    assert_private_image_headers(listing)
    assert listing.json()["endingCode"] == code
    assert len(listing.json()["images"]) == len(names)

    for index, name in enumerate(names, start=1):
        expected = (directory / name).read_bytes()

        response = client.get(f"{base}/{index}")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert_private_image_headers(response)

        assert hashlib.sha256(response.content).digest() == (
            hashlib.sha256(expected).digest()
        )

    assert repository.load_state(sid) == before


# Issue #192 - E30 player consent

# Issue #210 - Verify both consent endpoints.
@pytest.fixture(
    params=["consent", "evidence/E30/consent"],
    ids=["alias", "legacy"],
)
def consent_path(request):
    return request.param



def test_e30_consent_unapproved_by_default(runtime, consent_path):
    app, client, repository, sid, _ = runtime

    prepare(runtime)

    before = repository.load_state(sid)

    response = client.get(f"/api/games/{sid}")

    assert response.status_code == 200
    assert response.json()["e30ConsentAvailable"] is False
    assert response.json()["e30ConsentGranted"] is False

    response = client.post(
        f"/api/games/{sid}/{consent_path}",
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert response.status_code == 409
    assert repository.load_state(sid) == before


def test_e30_consent_records_player_choice_only(runtime, consent_path):
    app, client, repository, sid, _ = runtime

    prepare(runtime)

    # Synthetic approval provider for isolated integration testing.
    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)
    url = f"/api/games/{sid}/{consent_path}"

    response = client.get(f"/api/games/{sid}")

    assert response.status_code == 200
    assert response.json()["e30ConsentAvailable"] is True
    assert response.json()["e30ConsentGranted"] is False

    response = client.post(
        url,
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["e30ConsentGranted"] is True
    assert response.json()["e30ConsentAvailable"] is False
    assert response.headers["cache-control"] == "private, no-store"

    after = repository.load_state(sid)

    assert after.e30_player_consent is True
    assert after.revision == before.revision + 1
    assert after.evidence == before.evidence
    assert after.score == before.score
    assert after.flags == before.flags
    assert after.document_grants == before.document_grants
    assert after.queued_story_events == before.queued_story_events
    assert "E30" not in after.evidence
    assert "consent_and_safety_verified" not in after.flags

    assert client.get(
        f"/api/games/{sid}/evidence/E30"
    ).status_code == 404

    assert client.post(
        f"/api/games/{sid}/evidence/E30/collect"
    ).status_code == 422

    # Replay with the current revision must not mutate the state.
    repeated = client.post(
        url,
        json={
            "expectedRevision": after.revision,
            "consent": True,
        },
    )

    assert repeated.status_code == 200
    assert repository.load_state(sid) == after


def test_e30_consent_missing_prerequisites(runtime, consent_path):
    app, client, repository, sid, _ = runtime

    prepare(runtime, full=False)

    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)

    response = client.get(f"/api/games/{sid}")

    assert response.json()["e30ConsentAvailable"] is False

    response = client.post(
        f"/api/games/{sid}/{consent_path}",
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert response.status_code == 409
    assert repository.load_state(sid) == before


@pytest.mark.parametrize("invalid_consent", [False, 1, "true", None])
def test_e30_consent_requires_explicit_boolean(
    runtime,
    invalid_consent,
    consent_path,
):
    app, client, repository, sid, _ = runtime

    prepare(runtime)

    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)

    response = client.post(
        f"/api/games/{sid}/{consent_path}",
        json={
            "expectedRevision": before.revision,
            "consent": invalid_consent,
        },
    )

    assert response.status_code == 422
    assert repository.load_state(sid) == before


def test_e30_consent_rejects_stale_revision(runtime, consent_path):
    app, client, repository, sid, _ = runtime

    prepare(runtime)

    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)

    response = client.post(
        f"/api/games/{sid}/{consent_path}",
        json={
            "expectedRevision": before.revision - 1,
            "consent": True,
        },
    )

    assert response.status_code == 409
    assert repository.load_state(sid) == before


def test_e30_consent_rejects_other_session(runtime, consent_path):
    app, _, repository, sid, _ = runtime

    prepare(runtime)

    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)

    with TestClient(app) as outsider:
        assert outsider.post("/api/games").status_code == 201

        response = outsider.post(
            f"/api/games/{sid}/{consent_path}",
            json={
                "expectedRevision": before.revision,
                "consent": True,
            },
        )

        assert response.status_code == 404

    assert repository.load_state(sid) == before


def test_e30_consent_approval_failure_is_fail_closed(runtime, consent_path):
    app, client, repository, sid, _ = runtime

    prepare(runtime)

    def unavailable(state):
        raise RuntimeError("Synthetic approval service failure")

    app.state.e30_approval_check = unavailable

    before = repository.load_state(sid)

    response = client.get(f"/api/games/{sid}")

    assert response.status_code == 200
    assert response.json()["e30ConsentAvailable"] is False

    response = client.post(
        f"/api/games/{sid}/{consent_path}",
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert response.status_code == 409
    assert repository.load_state(sid) == before


def test_e30_consent_rejects_finished_game(runtime, consent_path):
    app, client, repository, sid, _ = runtime

    finish_image_test_game(runtime, "FULL")

    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)

    response = client.post(
        f"/api/games/{sid}/{consent_path}",
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert response.status_code == 409
    assert repository.load_state(sid) == before

@pytest.mark.parametrize(
    ("first_path", "second_path"),
    [
        ("consent", "evidence/E30/consent"),
        ("evidence/E30/consent", "consent"),
    ],
    ids=["alias-to-legacy", "legacy-to-alias"],
)
def test_e30_consent_cross_endpoint_idempotency(
    runtime,
    first_path,
    second_path,
):
    app, client, repository, sid, _ = runtime

    prepare(runtime)
    app.state.e30_approval_check = lambda state: True

    before = repository.load_state(sid)

    first = client.post(
        f"/api/games/{sid}/{first_path}",
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert first.status_code == 200
    assert first.json()["e30ConsentGranted"] is True
    assert first.headers["cache-control"] == "private, no-store"

    after = repository.load_state(sid)

    assert after.revision == before.revision + 1
    assert after.e30_player_consent is True

    second = client.post(
        f"/api/games/{sid}/{second_path}",
        json={
            "expectedRevision": after.revision,
            "consent": True,
        },
    )

    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["cache-control"] == "private, no-store"
    assert repository.load_state(sid) == after

    # A stale request must not change the persisted state.
    stale = client.post(
        f"/api/games/{sid}/{second_path}",
        json={
            "expectedRevision": before.revision,
            "consent": True,
        },
    )

    assert stale.status_code == 409
    assert repository.load_state(sid) == after

    # Consent alone must not unlock protected content.
    assert after.evidence == before.evidence
    assert after.score == before.score
    assert after.flags == before.flags
    assert after.document_grants == before.document_grants
    assert after.queued_story_events == before.queued_story_events
    assert "E30" not in after.evidence
