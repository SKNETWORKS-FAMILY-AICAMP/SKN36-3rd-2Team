
"""Import CASE-001 character relationships."""

import csv
import hashlib
import io
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import (
    Case,
    Character,
    Evidence,
    CharacterRelationship,
)


EXPECTED_COUNT = 58
SOURCE_NAME = "case001_1120"
DATASET_NAME = "relationships"

REQUIRED_COLUMNS = {
    "from_type",
    "from_id",
    "to_type",
    "to_id",
    "relationship",
    "public_from_stage",
    "source_basis",
    "period",
}

EXPECTED_TARGET_TYPES = {
    "npc": 11,
    "evidence": 34,
    "person": 13,
}

EXPECTED_STAGES = {
    "S1": 12,
    "S2": 31,
    "S3": 15,
}


def load_relationships(path: Path):
    """CSV 검증 및 Import 레코드 생성."""

    try:
        if not path.is_file():
            raise CommandError(f"Source not found: {path}")

        if path.stat().st_size > 1_000_000:
            raise CommandError("Source exceeds 1 MB")

        raw = path.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()

        reader = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig")),
            strict=True,
        )

        columns = reader.fieldnames or []

        if (
            len(columns) != len(set(columns))
            or set(columns) != REQUIRED_COLUMNS
        ):
            raise CommandError(
                "Unexpected or duplicate CSV columns"
            )

        rows = list(reader)

    except (OSError, UnicodeError, csv.Error) as exc:
        raise CommandError(
            f"Unable to read source: {exc}"
        ) from exc

    if len(rows) != EXPECTED_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_COUNT} rows, "
            f"found {len(rows)}"
        )

    prepared = []
    relation_keys = set()
    target_counts = Counter()
    stage_counts = Counter()

    for line_number, row in enumerate(rows, start=2):
        if (
            None in row
            or any(value is None for value in row.values())
        ):
            raise CommandError(
                f"Malformed CSV row: {line_number}"
            )

        values = {
            key: value.strip()
            for key, value in row.items()
        }

        source_type = values["from_type"]
        source_id = values["from_id"]
        target_type = values["to_type"]
        target_id = values["to_id"]
        relationship = values["relationship"]
        stage = values["public_from_stage"]
        source_basis = values["source_basis"]
        period = values["period"]

        if source_type != "npc":
            raise CommandError(
                f"Invalid source type at row {line_number}"
            )

        if source_id not in {
            f"C{number:02d}"
            for number in range(1, 11)
        }:
            raise CommandError(
                f"Invalid NPC at row {line_number}"
            )

        if target_type not in EXPECTED_TARGET_TYPES:
            raise CommandError(
                f"Invalid target type at row {line_number}"
            )

        if not target_id or len(target_id) > 100:
            raise CommandError(
                f"Invalid target ID at row {line_number}"
            )

        if (
            target_type == "npc"
            and source_id == target_id
        ):
            raise CommandError(
                f"Self-reference at row {line_number}"
            )

        if not relationship:
            raise CommandError(
                f"Empty relationship at row {line_number}"
            )

        if stage not in EXPECTED_STAGES:
            raise CommandError(
                f"Invalid public stage at row {line_number}"
            )

        if not source_basis or not period:
            raise CommandError(
                f"Missing metadata at row {line_number}"
            )

        # 동일 관계의 기간 차이는 허용합니다.
        relation_key = (
            source_id,
            target_type,
            target_id,
            relationship,
            stage,
            period,
        )

        if relation_key in relation_keys:
            raise CommandError(
                f"Duplicate relationship at row {line_number}"
            )

        relation_keys.add(relation_key)
        target_counts[target_type] += 1
        stage_counts[stage] += 1

        prepared.append({
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "relationship": row["relationship"],
            "public_from_stage": int(stage[1:]),
            "source_line": line_number,
            "metadata": {
                "import_source": SOURCE_NAME,
                "import_dataset": DATASET_NAME,
                "source_sha256": source_hash,
                "source_line": line_number,
                "source_from_type": source_type,
                "source_public_from_stage": stage,
                "source_basis": row["source_basis"],
                "source_period": row["period"],
                "runtime_enabled": False,
                "canon_approved": False,
            },
        })

    if dict(target_counts) != EXPECTED_TARGET_TYPES:
        raise CommandError("Target type distribution mismatch")

    if dict(stage_counts) != EXPECTED_STAGES:
        raise CommandError("Public stage distribution mismatch")

    return prepared


class Command(BaseCommand):
    help = (
        "Import CASE-001 character relationships "
        "(Dry Run by default)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            required=True,
            type=Path,
        )
        parser.add_argument(
            "--apply",
            action="store_true",
        )

    def handle(self, *args, **options):
        records = load_relationships(options["source"])

        created = 0
        existing = 0

        try:
            with transaction.atomic():
                case = Case.objects.filter(
                    case_id="CASE-001"
                ).first()

                if case is None:
                    raise CommandError(
                        "CASE-001 missing. Import foundation first."
                    )

                if case.status != Case.Status.DRAFT:
                    raise CommandError(
                        "Import requires DRAFT case"
                    )

                characters = {
                    obj.character_id: obj
                    for obj in Character.objects.filter(case=case)
                }

                evidences = set(
                    Evidence.objects.filter(case=case)
                    .values_list("evidence_id", flat=True)
                )

                if set(characters) != {
                    f"C{number:02d}"
                    for number in range(1, 11)
                }:
                    raise CommandError(
                        "Foundation NPCs are incomplete"
                    )

                for record in records:
                    target_type = record["target_type"]
                    target_id = record["target_id"]

                    if (
                        target_type == "npc"
                        and target_id not in characters
                    ):
                        raise CommandError(
                            f"Unknown target NPC: {target_id}"
                        )

                    if (
                        target_type == "evidence"
                        and target_id not in evidences
                    ):
                        raise CommandError(
                            f"Unknown evidence: {target_id}"
                        )

                # 기존 Import 레코드는 원본 행 번호로 식별합니다.
                managed_by_line = {}
                unmanaged_keys = set()

                stored = (
                    CharacterRelationship.objects
                    .filter(source_character__case=case)
                    .select_related("source_character")
                )

                for item in stored:
                    metadata = item.metadata

                    if not isinstance(metadata, dict):
                        raise CommandError(
                            "Invalid existing relationship metadata"
                        )

                    if (
                        metadata.get("import_source") == SOURCE_NAME
                        and metadata.get("import_dataset") == DATASET_NAME
                    ):
                        line = metadata.get("source_line")

                        if (
                            not isinstance(line, int)
                            or line in managed_by_line
                        ):
                            raise CommandError(
                                "Invalid or duplicate source line"
                            )

                        managed_by_line[line] = item

                    else:
                        unmanaged_keys.add((
                            item.source_character.character_id,
                            item.target_type,
                            item.target_id,
                            item.relationship,
                        ))

                source_lines = {
                    record["source_line"]
                    for record in records
                }

                if set(managed_by_line) - source_lines:
                    raise CommandError(
                        "Unexpected existing imported records"
                    )

                for record in records:
                    source_id = record["source_id"]
                    source_character = characters[source_id]

                    expected = {
                        "source_character": source_character,
                        "target_type": record["target_type"],
                        "target_id": record["target_id"],
                        "relationship": record["relationship"],
                        "public_from_stage": (
                            record["public_from_stage"]
                        ),
                        "is_active": False,
                        "metadata": record["metadata"],
                    }

                    natural_key = (
                        source_id,
                        record["target_type"],
                        record["target_id"],
                        record["relationship"],
                    )

                    if natural_key in unmanaged_keys:
                        raise CommandError(
                            "Conflicting unmanaged relationship "
                            f"at source row {record['source_line']}"
                        )

                    item = managed_by_line.get(
                        record["source_line"]
                    )

                    if item is not None:
                        if (
                            item.source_character_id
                            != source_character.pk
                            or item.target_type
                            != expected["target_type"]
                            or item.target_id
                            != expected["target_id"]
                            or item.relationship
                            != expected["relationship"]
                            or item.public_from_stage
                            != expected["public_from_stage"]
                            or item.is_active is not False
                            or item.metadata
                            != expected["metadata"]
                        ):
                            raise CommandError(
                                "Existing relationship conflict "
                                f"at source row {record['source_line']}"
                            )

                        existing += 1
                        continue

                    item = CharacterRelationship(**expected)
                    item.full_clean()
                    item.save()
                    created += 1

                self.stdout.write(
                    f"Source records: {len(records)}"
                )
                self.stdout.write(
                    f"New relationships: {created}"
                )
                self.stdout.write(
                    f"Existing relationships: {existing}"
                )

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Relationship import failed: {exc}"
            ) from exc

        if options["apply"]:
            self.stdout.write(
                self.style.SUCCESS("IMPORT COMMITTED")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN - ALL CHANGES ROLLED BACK"
                )
            )
