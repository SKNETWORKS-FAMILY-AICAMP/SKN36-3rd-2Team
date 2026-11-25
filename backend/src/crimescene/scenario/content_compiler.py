"""Issue #165 - CASE-001 expansion content compiler."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from crimescene.scenario.acquisition_policy import (
    AcquisitionPolicy,
    AcquisitionRoute,
)
from crimescene.scenario.loaders.evidence_loader import load_evidence_rules
from crimescene.scenario.schemas.access_policy import AccessPolicy

LEGACY_IDS = frozenset(f"E{i:02d}" for i in range(1, 11))
EXTENDED_IDS = frozenset(f"E{i:02d}" for i in range(11, 31))
ALL_IDS = LEGACY_IDS | EXTENDED_IDS
NPC_IDS = frozenset(f"C{i:02d}" for i in range(1, 11))

CONTENT_VERSION = "case001_1120"

PROPOSED_SCORES = {
    "E11": 1,
    "E12": 1,
    "E13": 2,
    "E14": 3,
    "E15": 1,
    "E16": 2,
    "E17": 3,
    "E18": 2,
    "E19": 1,
    "E20": 2,
    "E21": 2,
    "E22": 2,
    "E23": 3,
    "E24": 2,
    "E25": 2,
    "E26": 3,
    "E27": 3,
    "E28": 3,
    "E29": 3,
    "E30": 3,
}

CSV_SOURCES = {
    "extended_evidence": ("05_EVIDENCE_E11_E30.csv", 20),
    "evidence_links": ("07_EVIDENCE_LINKS.csv", 23),
    "knowledge_cards": ("08_NPC_KNOWLEDGE_CARDS.csv", 100),
    "smalltalk_cards": ("08_NPC_SMALLTALK_CARDS.csv", 40),
    "dialogue_triggers": ("09_NPC_DIALOGUE_TRIGGERS.csv", 166),
    "relationships": ("10_RELATIONSHIPS.csv", 58),
    "objectives": ("12_OBJECTIVES_AND_HINTS.csv", 25),
}


def read_csv(path: Path, expected_count: int):
    raw = path.read_bytes()
    reader = csv.DictReader(
        io.StringIO(raw.decode("utf-8-sig"))
    )

    columns = reader.fieldnames or []

    if not columns or len(columns) != len(set(columns)):
        raise ValueError(f"Invalid columns: {path.name}")

    rows = list(reader)

    if len(rows) != expected_count:
        raise ValueError(f"Unexpected row count: {path.name}")

    if any(
        None in row or any(v is None for v in row.values())
        for row in rows
    ):
        raise ValueError(f"Malformed CSV: {path.name}")

    return rows, hashlib.sha256(raw).hexdigest()


def validate_unique_ids(rows, key, expected=None):
    ids = [row[key].strip() for row in rows]

    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError(f"Invalid or duplicate IDs: {key}")

    if expected is not None and set(ids) != set(expected):
        raise ValueError(f"Unexpected ID set: {key}")

    return set(ids)


def make_route(
    evidence_id,
    chapter,
    suffix,
    action,
    *,
    evidence=(),
    presentations=(),
    flags=(),
    character=None,
):
    return AcquisitionRoute(
        route_id=f"{evidence_id}-{suffix}",
        chapter=chapter,
        action_flag=f"ACT_{action}",
        policy=AccessPolicy(
            required_evidence=list(evidence),
            required_presentations=list(presentations),
            required_flags=list(flags),
            required_ending=None,
            required_topics=[],
            required_disclosed_cards=[],
            required_character=character,
        ),
    )


def proposed_routes(eid, chapter):
    """Candidate routes. Never activate without approval."""

    def route(suffix, action, **conditions):
        return make_route(
            eid,
            chapter,
            suffix,
            action,
            **conditions,
        )

    routes = {
        "E11": [
            route("A", "PHOTO_ORIGINAL_VERIFIED"),
        ],
        "E12": [
            route(
                "A", "STUDENT_RECORD_INSPECTED",
                evidence=["E11"],
            ),
            route(
                "B", "C07_STATEMENT_VERIFIED",
                character="C07",
            ),
        ],
        "E13": [
            route(
                "A", "FOUNDATION_RECORD_ACCESSED",
                evidence=["E12"],
            ),
        ],
        "E14": [
            route(
                "A", "ACADEMIC_RECORD_INSPECTED",
                evidence=["E13"],
            ),
            route(
                "B", "C08_STATEMENT_VERIFIED",
                character="C08",
            ),
        ],
        "E15": [
            route(
                "A", "C05_INTERVIEW_COMPLETED",
                evidence=["E14"],
                character="C05",
            ),
        ],
        "E16": [
            route(
                "A", "C09_VIDEO_ORIGINAL_VERIFIED",
                evidence=["E11", "E15"],
                character="C09",
            ),
        ],
        "E17": [
            route(
                "A", "ACCOUNTING_ACCESS_VERIFIED",
                evidence=["E13"],
            ),
        ],
        "E18": [
            route(
                "A", "POSTAL_RECORD_INSPECTED",
                evidence=["E14", "E16"],
                presentations=["C08:E14"],
                flags=["ACT_SC0203_COMPLETED"],
            ),
        ],
        "E19": [
            route("A", "RECEPTION_RECORD_INSPECTED"),
            route(
                "B", "C07_PACKAGE_STATEMENT_VERIFIED",
                character="C07",
            ),
        ],
        "E20": [
            route(
                "A", "OFFICE_DATA_ACCESSED",
                evidence=["E19"],
            ),
        ],
        "E21": [
            route("A", "CARD_OPERATION_VERIFIED"),
        ],
        "E22": [
            route(
                "A", "C04_SECURITY_QUESTION_VERIFIED",
                character="C04",
            ),
            route(
                "B", "SECURITY_COMMAND_INSPECTED",
                evidence=["E04"],
            ),
        ],
        "E23": [
            route(
                "A", "SENSOR_RECORD_INSPECTED",
                evidence=["E21"],
            ),
            route(
                "B", "SENSOR_RECORD_INSPECTED",
                evidence=["E22"],
            ),
        ],
        "E24": [
            route(
                "A", "REFLECTION_ORIGINAL_VERIFIED",
                evidence=["E23"],
            ),
        ],
        "E25": [
            route(
                "A", "EMERGENCY_DOOR_RECORD_INSPECTED",
                evidence=["E23"],
            ),
            route(
                "B", "SECURITY_RECORD_ACCESS_VERIFIED",
            ),
        ],
        "E26": [
            route(
                "A", "AUDIT_LOG_ACCESS_VERIFIED",
                evidence=["E20"],
            ),
        ],
        "E27": [
            route(
                "A", "ACCOUNTING_VERSIONS_COMPARED",
                evidence=["E17", "E26"],
            ),
        ],
        "E28": [
            route(
                "A", "C06_ALIBI_INTERVIEW_COMPLETED",
                evidence=["E24", "E25"],
                character="C06",
            ),
        ],
        "E29": [
            route(
                "A", "RECOVERED_AUDIO_VERIFIED",
                evidence=["E26", "E28"],
            ),
        ],
        "E30": [
            route(
                "A", "SC0405_STATEMENT_ACCESSED",
                evidence=["E14", "E16", "E18"],
                flags=["consent_and_safety_verified"],
            ),
        ],
    }

    return AcquisitionPolicy(
        evidence_id=eid,
        routes=routes[eid],
    )


def compile_evidence(legacy, extended):
    if set(legacy) != LEGACY_IDS:
        raise ValueError("Legacy evidence ID mismatch")

    validate_unique_ids(
        extended,
        "evidence_id",
        EXTENDED_IDS,
    )

    result = {}

    for eid, rule in sorted(legacy.items()):
        result[eid] = {
            "origin": "case001_v7_1",
            "score": rule.score,
            "score_status": "LEGACY",
            "legacy_rule": rule.model_dump(mode="json"),
        }

    for row in extended:
        eid = row["evidence_id"].strip()
        holder = row["holder_npc_id"].strip()
        chapter = row["chapter"].strip()

        if holder not in NPC_IDS:
            raise ValueError(f"Unknown evidence holder: {eid}")

        if not row["title"].strip():
            raise ValueError(f"Missing title: {eid}")

        if row["access_scope"].strip() != "UNLOCKED_ONLY":
            raise ValueError(f"Invalid access scope: {eid}")

        policy = proposed_routes(eid, chapter)

        for route in policy.routes:
            required = set(route.policy.required_evidence)

            if not required.issubset(ALL_IDS) or eid in required:
                raise ValueError(f"Invalid prerequisite: {eid}")

        result[eid] = {
            "origin": CONTENT_VERSION,
            "name": row["title"].strip(),
            "holder": holder,
            "chapter": chapter,
            "proposed_score": PROPOSED_SCORES[eid],
            "score_status": "PROPOSED",
            "runtime_enabled": False,
            "contract_approved": False,
            "acquisition_policy_candidate": (
                policy.model_dump(mode="json")
            ),
            "source": row,
        }

    return result


def compile_content(source: Path, legacy_root: Path):
    source = source.resolve()
    legacy_root = legacy_root.resolve()

    paths = list(legacy_root.rglob("evidence_rules.json"))

    if len(paths) != 1:
        raise ValueError("Expected one legacy evidence catalog")

    legacy = load_evidence_rules(paths[0])
    data = {}
    hashes = {}

    for key, (filename, expected) in CSV_SOURCES.items():
        rows, digest = read_csv(source / filename, expected)
        data[key] = rows
        hashes[filename] = digest

    evidence = compile_evidence(
        legacy,
        data["extended_evidence"],
    )

    for row in data["evidence_links"]:
        if (
            row["from_evidence"] not in ALL_IDS
            or row["to_evidence"] not in ALL_IDS
        ):
            raise ValueError("Unknown evidence link reference")

    cards = (
        data["knowledge_cards"]
        + data["smalltalk_cards"]
    )

    validate_unique_ids(cards, "card_id")

    for row in cards:
        npc_id = row["npc_id"]

        if (
            npc_id not in NPC_IDS
            or not row["card_id"].startswith(f"K-{npc_id}-")
        ):
            raise ValueError("NPC card ownership mismatch")

    for row in data["dialogue_triggers"]:
        if row["npc_id"] not in NPC_IDS:
            raise ValueError("Unknown dialogue NPC")

        if row["stage"] not in {"1", "2", "3"}:
            raise ValueError("Invalid dialogue stage")

        if row["output_mode"] not in {"fixed", "reference"}:
            raise ValueError("Invalid dialogue output mode")

    scene_path = source / "04_SCENES.json"
    raw = scene_path.read_bytes()
    scene_data = json.loads(raw.decode("utf-8-sig"))
    scenes = scene_data["scenes"]

    if len(scenes) != 30:
        raise ValueError("Unexpected scene count")

    validate_unique_ids(scenes, "scene_id")
    validate_unique_ids(data["objectives"], "objective_id")

    hashes[scene_path.name] = hashlib.sha256(raw).hexdigest()
    hashes["legacy/evidence_rules.json"] = hashlib.sha256(
        paths[0].read_bytes()
    ).hexdigest()

    return {
        "case_id": "CASE-001",
        "content_version": CONTENT_VERSION,
        "status": "DRAFT",
        "runtime_enabled": False,
        "source_hashes": hashes,
        "evidence": evidence,
        "npc_cards": cards,
        "dialogue_triggers": data["dialogue_triggers"],
        "relationships": data["relationships"],
        "evidence_links": data["evidence_links"],
        "objectives": data["objectives"],
        "scenes": scenes,
        "legacy_score": sum(
            rule.score for rule in legacy.values()
        ),
        "proposed_extended_score": sum(
            PROPOSED_SCORES.values()
        ),
        "review_required": [
            "ACQUISITION_ACTION_BINDINGS",
            "EVIDENCE_SCORE_POLICY",
            "EVIDENCE_CANON",
            "NPC_DISCLOSURE",
            "DIALOGUE_TRIGGER_POLICY",
            "RELATIONSHIP_ACCESS_POLICY",
            "SCENE_AND_OBJECTIVE_CONTRACT",
            "ENDING_RULES",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    catalog = compile_content(args.source, args.legacy)

    output = args.output.resolve()

    if ".local" not in output.parts:
        raise ValueError("Output must remain under .local")

    output.parent.mkdir(parents=True, exist_ok=True)

    # Exclusive creation prevents accidental replacement.
    with output.open("x", encoding="utf-8") as f:
        json.dump(
            catalog,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("CONTENT VERSION:", catalog["content_version"])
    print("STATUS:", catalog["status"])
    print("RUNTIME ENABLED:", catalog["runtime_enabled"])

    for key in (
        "evidence",
        "npc_cards",
        "dialogue_triggers",
        "relationships",
        "evidence_links",
        "objectives",
        "scenes",
        "source_hashes",
    ):
        print(key.upper(), len(catalog[key]))

    print("LEGACY SCORE:", catalog["legacy_score"])
    print(
        "PROPOSED TOTAL SCORE:",
        catalog["legacy_score"]
        + catalog["proposed_extended_score"],
    )

    print("CONTENT COMPILATION COMPLETE")


if __name__ == "__main__":
    main()
