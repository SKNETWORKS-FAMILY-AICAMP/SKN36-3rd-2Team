"""Release-bound objective and inference configuration."""

import csv
import hashlib
import json
import re
from pathlib import Path

from crimescene.scenario.investigation_progress import (
    InferenceRule,
    ObjectiveRule,
)

VERSION = "case001_1120"

INFERENCE_SELECTION = (
    ("E13", "E14", "INF_2016_COVERUP", "CH02"),
    ("E11", "E16", "INF_2016_VIDEO", "CH02"),
    ("E13", "E17", "INF_FUND_CODE", "CH02"),
    ("E16", "E18", "INF_2016_FORCED_DEPARTURE", "CH02"),
    ("E18", "E19", "INF_RECEIPT_SAME_FORM", "CH02"),
    ("E21", "E23", "INF_ACCESS_WINDOW", "CH03"),
    ("E22", "E23", "INF_ACCESS_WINDOW", "CH03"),
    ("E23", "E24", "INF_HALLWAY_WINDOW", "CH03"),
    ("E23", "E25", "INF_EXIT_WINDOW", "CH03"),
    ("E24", "E28", "INF_C02_ALIBI_CONFLICT", "CH03"),
)

OBJECTIVE_SELECTION = frozenset({
    "OBJ_FIND_STUDENT_RECORD",
    "OBJ_CHECK_SCHOLARSHIP",
    "OBJ_CHECK_SIGNOFF",
    "OBJ_TALK_SEOMIRAN",
    "OBJ_CHECK_2016_VIDEO",
    "OBJ_VERIFY_DEPARTURE",
    "OBJ_CHECK_DRAFT_EMAIL",
    "OBJ_FIND_CARD_USER",
    "OBJ_FIND_SHUTDOWN_REASON",
    "OBJ_RECONSTRUCT_ROUTE",
    "OBJ_CHECK_REFLECTION",
})


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def read_csv(path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def extract_evidence(value):
    return frozenset(
        re.findall(r"\bE\d{2}\b", value or "")
    )


def build_progression_contract(*, manifest, source_dir):
    if manifest["content_version"] != VERSION:
        raise ValueError("Content version mismatch")

    if manifest["scope"] != "LOCAL_INTEGRATION_TEST":
        raise ValueError("Invalid publication scope")

    source_dir = Path(source_dir)

    link_path = source_dir / "07_EVIDENCE_LINKS.csv"
    objective_path = source_dir / "12_OBJECTIVES_AND_HINTS.csv"
    scene_path = source_dir / "04_SCENES.json"

    source_hashes = {
        path.name: hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (link_path, objective_path, scene_path)
    }

    links = read_csv(link_path)
    objectives = read_csv(objective_path)

    if len(links) != 23 or len(objectives) != 25:
        raise ValueError("Unexpected progression source count")

    published = set(manifest["approved_evidence"])

    inference_contracts = {}
    selection = INFERENCE_SELECTION

    e26_approved = manifest.get(
        "approved_e26_inference",
        False,
    )

    if type(e26_approved) is not bool:
        raise PermissionError("Invalid E26 inference approval")

    if e26_approved:
        from crimescene.api.expanded_acquisition_runtime import (
            validate_e26_release_contract,
        )

        if not validate_e26_release_contract(manifest):
            raise PermissionError("E26-A release approval required")

        selection = (
            *selection,
            (
                "E20",
                "E26",
                "INF_POST_EVENT_DELETE",
                "CH03",
            ),
        )

    for source, target, inf, chapter in selection:
        matching = [
            (i, row)
            for i, row in enumerate(links, start=1)
            if row["from_evidence"] == source
            and row["to_evidence"] == target
            and row["resulting_inference"] == inf
        ]

        if len(matching) != 1:
            raise ValueError(f"Link source mismatch: {inf}")

        index, row = matching[0]

        ids = {source, target}
        expected_mode = "pair"

        if inf == "INF_2016_FORCED_DEPARTURE":
            ids.add("E14")
            expected_mode = "triple"

            scenes = json.loads(
                scene_path.read_text(encoding="utf-8-sig")
            )["scenes"]

            scene = next(
                item for item in scenes
                if item["scene_id"] == "SC-0206"
            )

            if not ids.issubset(
                extract_evidence(scene["entry_condition_proposal"])
            ):
                raise ValueError("SC0206 requirements mismatch")

        raw_mode = row["presentation_mode"].strip().lower()

        actual_mode = {
            "\ubcf5\uc218(2\uac1c)": "pair",
            "\ubcf5\uc218(3\uac1c)": "triple",
            "pair": "pair",
            "triple": "triple",
        }.get(raw_mode)

        if actual_mode != expected_mode:
            raise ValueError(f"Presentation mode mismatch: {inf}")

        if not ids.issubset(published):
            raise PermissionError("Unpublished inference evidence")

        required_flags = frozenset()

        if ids.intersection({"E26", "E30"}):
            if (
                e26_approved is not True
                or ids != {"E20", "E26"}
                or inf != "INF_POST_EVENT_DELETE"
                or chapter != "CH03"
                or row["unlock_event"] != "STORY_026"
                or row["needs_canon_approval"] != "YES"
            ):
                raise PermissionError("Protected inference evidence")

            scenes = json.loads(
                scene_path.read_text(encoding="utf-8-sig")
            )["scenes"]

            candidates = [
                item for item in scenes
                if item["scene_id"] == "SC-0306"
            ]

            if len(candidates) != 1:
                raise ValueError("SC0306 source mismatch")

            scene = candidates[0]
            condition = scene["entry_condition_proposal"]

            if (
                scene["chapter"] != "CH03"
                or extract_evidence(condition)
                != frozenset({"E20", "E26"})
                or "\uad6c\ud68d A" not in condition
            ):
                raise PermissionError("Invalid SC0306 scope")

            required_flags = frozenset({
                "ACT_AUDIT_LOG_ACCESS_VERIFIED"
            })

        rule_id = f"LINK-{index:03d}"

        InferenceRule(
            rule_id=rule_id,
            inference_id=inf,
            chapter=chapter,
            evidence_ids=frozenset(ids),
            required_flags=required_flags,
        )

        inference_contracts[rule_id] = {
            "rule_id": rule_id,
            "inference_id": inf,
            "chapter": chapter,
            "evidence_ids": sorted(ids),
            "required_flags": sorted(required_flags),
            "source_row_sha256": digest(row),
        }

    objective_contracts = {}

    for row in objectives:
        oid = row["objective_id"]

        if oid not in OBJECTIVE_SELECTION:
            continue

        required = extract_evidence(row["unlocked_by_evidence"])
        targets = extract_evidence(row["target_evidence"])

        if not targets:
            raise ValueError(f"Objective target missing: {oid}")

        if not (required | targets).issubset(published):
            raise PermissionError(f"Unpublished objective: {oid}")

        if (required | targets).intersection({"E26", "E30"}):
            raise PermissionError("Protected objective")

        if oid in objective_contracts:
            raise ValueError("Duplicate objective")

        ObjectiveRule(
            objective_id=oid,
            chapter=row["chapter"],
            required_evidence=required,
            target_evidence=targets,
        )

        objective_contracts[oid] = {
            "objective_id": oid,
            "chapter": row["chapter"],
            "required_evidence": sorted(required),
            "target_evidence": sorted(targets),
            "completion_flags": [],
            "source_row_sha256": digest(row),
        }

    if len(inference_contracts) != 10 + int(e26_approved):
        raise ValueError("Incomplete inference selection")

    if set(objective_contracts) != OBJECTIVE_SELECTION:
        raise ValueError("Incomplete objective selection")

    return {
        "content_version": VERSION,
        "scope": "LOCAL_INTEGRATION_TEST",
        "source_hashes": source_hashes,
        "inferences": inference_contracts,
        "objectives": objective_contracts,
    }


def configure_e26_story_event(*, app, manifest):
    """Configure only an explicitly published STORY_026 event."""

    approved = manifest.get("approved_e26_inference", False)
    contract = manifest.get("approved_e26_story_event")

    if type(approved) is not bool:
        raise PermissionError("Invalid E26 inference approval")

    if not approved:
        if contract is not None:
            raise PermissionError("Unapproved E26 story event")
        return

    if (
        manifest.get("content_version") != VERSION
        or manifest.get("scope") != "LOCAL_INTEGRATION_TEST"
        or manifest.get("approved_e26_sections") != ["A"]
        or getattr(
            app.state,
            "e26_section_a_approved",
            False,
        ) is not True
    ):
        raise PermissionError("E26 section approval required")

    expected_keys = {
        "source_story_id",
        "event_key",
        "chapter",
        "section",
        "payload_sha256",
    }

    if (
        not isinstance(contract, dict)
        or set(contract) != expected_keys
        or contract["source_story_id"] != "STORY_026"
        or contract["chapter"] != "CH03"
        or contract["section"] != "A"
        or not isinstance(contract["payload_sha256"], str)
        or not re.fullmatch(
            r"[a-f0-9]{64}",
            contract["payload_sha256"],
        )
    ):
        raise PermissionError("Invalid STORY_026 release contract")

    from crimescene.api.django_content_client import (
        DjangoContentClient,
        ApprovedStoryEvent,
    )
    from crimescene.api.story_event_conditions import (
        StoryEventConditions,
    )
    from crimescene.api.story_event_delivery_gate import (
        StoryEventBinding,
        story_event_payload_sha256,
    )

    binding = StoryEventBinding(
        source_story_id="STORY_026",
        event_key=contract["event_key"],
        chapter="CH03",
        payload_sha256=contract["payload_sha256"],
    )

    django = getattr(app.state, "django_content_client", None)

    if not isinstance(django, DjangoContentClient):
        raise RuntimeError("Django content service unavailable")

    event = django.get_approved_story_event(
        "CASE-001",
        binding.event_key,
    )

    if (
        not isinstance(event, ApprovedStoryEvent)
        or event.event_key != binding.event_key
        or event.chapter != "CH03"
        or event.trigger_type != "EVIDENCE_COLLECTED"
        or set(event.required_evidence_ids) != {"E20", "E26"}
        or story_event_payload_sha256(event) != binding.payload_sha256
    ):
        raise PermissionError("STORY_026 payload mismatch")

    conditions = StoryEventConditions(
        story_id="STORY_026",
        chapter="CH03",
        all_evidence=frozenset({"E20", "E26"}),
        required_flags=frozenset({
            "ACT_AUDIT_LOG_ACCESS_VERIFIED",
            "INF_POST_EVENT_DELETE",
        }),
    )

    bindings = dict(
        getattr(app.state, "story_event_bindings", None) or {}
    )

    rules = dict(
        getattr(app.state, "story_event_conditions", None) or {}
    )

    if (
        binding.event_key in bindings
        or "STORY_026" in rules
        or any(
            item.source_story_id == "STORY_026"
            for item in bindings.values()
        )
    ):
        raise PermissionError("Duplicate STORY_026 configuration")

    bindings[binding.event_key] = binding
    rules["STORY_026"] = conditions

    app.state.story_event_bindings = bindings
    app.state.story_event_conditions = rules

    print("APPROVED STORY EVENT: STORY_026")


def configure_published_progression(
    *,
    app,
    manifest,
    source_dir,
):
    contract = manifest.get("approved_progression")

    if not isinstance(contract, dict):
        raise TypeError("Progression release unavailable")

    expected = build_progression_contract(
        manifest=manifest,
        source_dir=source_dir,
    )

    if contract != expected:
        raise PermissionError("Progression contract mismatch")

    configure_e26_story_event(
        app=app,
        manifest=manifest,
    )

    app.state.approved_inference_rules = tuple(
        InferenceRule(
            rule_id=item["rule_id"],
            inference_id=item["inference_id"],
            chapter=item["chapter"],
            evidence_ids=frozenset(item["evidence_ids"]),
            required_flags=frozenset(item["required_flags"]),
        )
        for item in contract["inferences"].values()
    )

    app.state.approved_objective_rules = tuple(
        ObjectiveRule(
            objective_id=item["objective_id"],
            chapter=item["chapter"],
            required_evidence=frozenset(item["required_evidence"]),
            target_evidence=frozenset(item["target_evidence"]),
            completion_flags=frozenset(item["completion_flags"]),
        )
        for item in contract["objectives"].values()
    )

    print(
        "APPROVED INFERENCES:",
        len(app.state.approved_inference_rules),
    )

    print(
        "APPROVED OBJECTIVES:",
        len(app.state.approved_objective_rules),
    )

    return contract
