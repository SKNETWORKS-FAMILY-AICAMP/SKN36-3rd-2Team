
"""CASE-001 legacy foundation importer.

Python 3.13 / Django 5.2
Default: transaction rollback (dry run).
"""

import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import (
    Case,
    Chapter,
    Character,
    Evidence,
    EvidencePrerequisite,
)


NPC_IDS = {f"C{i:02d}" for i in range(1, 11)}
EVIDENCE_IDS = {f"E{i:02d}" for i in range(1, 11)}


def load_sources(root: Path):
    if not root.is_dir():
        raise CommandError(f"Source directory not found: {root}")

    candidates = [
        child / "data"
        for child in root.iterdir()
        if child.is_dir() and (child / "data").is_dir()
    ]

    if len(candidates) != 1:
        raise CommandError("Expected exactly one legacy data directory")

    data_dir = candidates[0]

    def read_json(name):
        with (data_dir / name).open(encoding="utf-8-sig") as file:
            return json.load(file)

    registry = read_json("character_registry.json")
    characters = read_json("characters.json")
    evidence = read_json("evidence_rules.json")

    if not isinstance(registry, dict):
        raise CommandError("Invalid character registry")

    if not isinstance(characters, list) or not isinstance(evidence, dict):
        raise CommandError("Invalid source structure")

    character_map = {
        row["id"]: row
        for row in characters
    }

    if len(character_map) != len(characters):
        raise CommandError("Duplicate NPC IDs")

    if set(character_map) != NPC_IDS:
        raise CommandError("NPC ID mismatch")

    if not NPC_IDS.issubset(registry):
        raise CommandError("Missing NPC registry entries")

    if set(evidence) != EVIDENCE_IDS:
        raise CommandError("Baseline evidence ID mismatch")

    for npc_id, row in character_map.items():
        if not isinstance(row.get("name"), str) or not row["name"].strip():
            raise CommandError(f"Invalid NPC name: {npc_id}")

    for evidence_id, rule in evidence.items():
        if not isinstance(rule, dict):
            raise CommandError(f"Invalid evidence rule: {evidence_id}")

        score = rule.get("score")
        holder = rule.get("holder")
        prerequisites = rule.get("prerequisites")

        if type(score) is not int or score < 0:
            raise CommandError(f"Invalid score: {evidence_id}")

        if holder not in NPC_IDS:
            raise CommandError(f"Unknown holder: {evidence_id}")

        if not isinstance(prerequisites, list):
            raise CommandError(f"Invalid prerequisites: {evidence_id}")

        if len(prerequisites) != len(set(prerequisites)):
            raise CommandError(f"Duplicate prerequisites: {evidence_id}")

        if any(item not in EVIDENCE_IDS for item in prerequisites):
            raise CommandError(f"Unknown prerequisite: {evidence_id}")

    return character_map, evidence


class Command(BaseCommand):
    help = "Validate and import CASE-001 foundation data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--legacy-root",
            required=True,
            type=Path,
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit changes. Without this flag, rollback.",
        )

    def handle(self, *args, **options):
        try:
            characters, evidence_rules = load_sources(
                options["legacy_root"]
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(f"Source validation failed: {exc}") from exc

        created = {
            "case": 0,
            "chapter": 0,
            "character": 0,
            "evidence": 0,
            "prerequisite": 0,
        }

        def ensure(model, lookup, defaults, category):
            existing = model.objects.filter(**lookup).first()

            if existing is not None:
                return existing

            instance = model(**lookup, **defaults)
            instance.full_clean()
            instance.save()
            created[category] += 1
            return instance

        try:
            with transaction.atomic():
                case = ensure(
                    Case,
                    {"case_id": "CASE-001"},
                    {
                        "title": "마지막 기록: 졸업하지 못한 밤",
                        "status": Case.Status.DRAFT,
                    },
                    "case",
                )

                if case.status != Case.Status.DRAFT:
                    raise CommandError(
                        "Refusing to import into a non-DRAFT case"
                    )

                # Chapter titles remain technical placeholders
                # until final canonical titles are mapped.
                for number in range(5):
                    code = f"CH{number:02d}"

                    chapter = ensure(
                        Chapter,
                        {"case": case, "code": code},
                        {
                            "order": number,
                            "title": code,
                            "metadata": {
                                "title_pending": True,
                                "import_source": "legacy_bootstrap",
                            },
                        },
                        "chapter",
                    )

                    if chapter.order != number:
                        raise CommandError(
                            f"Chapter order mismatch: {code}"
                        )

                npc_map = {}

                for npc_id in sorted(characters):
                    source = characters[npc_id]
                    name = source["name"].strip()

                    npc = ensure(
                        Character,
                        {"case": case, "character_id": npc_id},
                        {
                            "name": name,
                            "profile": "",
                            "metadata": {
                                "import_source": "legacy_v7_1",
                            },
                        },
                        "character",
                    )

                    if npc.name != name:
                        raise CommandError(f"NPC mismatch: {npc_id}")

                    npc_map[npc_id] = npc

                evidence_map = {}

                for evidence_id in sorted(evidence_rules):
                    rule = evidence_rules[evidence_id]
                    holder = npc_map[rule["holder"]]

                    item = ensure(
                        Evidence,
                        {"case": case, "evidence_id": evidence_id},
                        {
                            "name": rule["name"],
                            "holder": holder,
                            "score": rule["score"],
                            "metadata": {
                                "import_source": "legacy_v7_1",
                            },
                        },
                        "evidence",
                    )

                    if (
                        item.name != rule["name"]
                        or item.holder_id != holder.pk
                        or item.score != rule["score"]
                    ):
                        raise CommandError(
                            f"Existing evidence mismatch: {evidence_id}"
                        )

                    evidence_map[evidence_id] = item

                for evidence_id, rule in evidence_rules.items():
                    dependent = evidence_map[evidence_id]

                    for prerequisite_id in rule["prerequisites"]:
                        prerequisite = evidence_map[prerequisite_id]

                        if EvidencePrerequisite.objects.filter(
                            dependent=dependent,
                            prerequisite=prerequisite,
                        ).exists():
                            continue

                        edge = EvidencePrerequisite(
                            dependent=dependent,
                            prerequisite=prerequisite,
                        )
                        edge.full_clean()
                        edge.save()
                        created["prerequisite"] += 1

                for category, count in created.items():
                    self.stdout.write(f"{category}: +{count}")

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(f"Import validation failed: {exc}") from exc

        if options["apply"]:
            self.stdout.write(
                self.style.SUCCESS("IMPORT COMMITTED")
            )
        else:
            self.stdout.write(
                self.style.WARNING("DRY RUN - ALL CHANGES ROLLED BACK")
            )
