
"""CASE-001 NPC dialogue trigger importer."""

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
    NPCDialogueTrigger,
)


EXPECTED_COUNT = 166

EXPECTED_NPC_COUNTS = {
    "C01": 25,
    "C02": 17,
    "C03": 14,
    "C04": 13,
    "C05": 15,
    "C06": 14,
    "C07": 13,
    "C08": 19,
    "C09": 14,
    "C10": 22,
}

REQUIRED_COLUMNS = {
    "npc_id",
    "stage",
    "trigger_type",
    "evidence_ids",
    "response_text",
    "tag",
    "next_stage",
    "repeat_variant",
    "draft_status",
    "source_basis",
    "condition_key",
    "output_order",
    "output_mode",
}

VALID_TRIGGER_TYPES = {
    "question",
    "verbal_only",
    "evidence",
    "evidence_combo",
}

VALID_OUTPUT_MODES = {"fixed", "reference"}


def load_dialogue_csv(path: Path):
    """원본 CSV 구조를 검증하고 안정적인 ID를 생성합니다."""

    try:
        if not path.is_file():
            raise CommandError(f"Source not found: {path}")

        if path.stat().st_size > 5_000_000:
            raise CommandError("Source file exceeds 5 MB")

        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()

        reader = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig"))
        )

        columns = reader.fieldnames or []

        if len(columns) != len(set(columns)):
            raise CommandError("Duplicate CSV columns")

        missing = REQUIRED_COLUMNS - set(columns)

        if missing:
            raise CommandError(
                f"Missing columns: {sorted(missing)}"
            )

        rows = list(reader)

    except (OSError, UnicodeError, csv.Error) as exc:
        raise CommandError(f"Invalid source CSV: {exc}") from exc

    if len(rows) != EXPECTED_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_COUNT} rows, found {len(rows)}"
        )

    npc_counters = Counter()
    prepared = []

    for line_number, row in enumerate(rows, start=2):
        if None in row or any(v is None for v in row.values()):
            raise CommandError(
                f"Malformed CSV row: {line_number}"
            )

        npc_id = row["npc_id"].strip()
        stage = row["stage"].strip()
        trigger_type = row["trigger_type"].strip()
        output_mode = row["output_mode"].strip()
        condition_key = row["condition_key"].strip()
        response_text = row["response_text"]
        output_order = row["output_order"].strip()
        next_stage = row["next_stage"].strip()

        if npc_id not in EXPECTED_NPC_COUNTS:
            raise CommandError(
                f"Unknown NPC at row {line_number}"
            )

        if stage not in {"1", "2", "3"}:
            raise CommandError(
                f"Invalid stage at row {line_number}"
            )

        if trigger_type not in VALID_TRIGGER_TYPES:
            raise CommandError(
                f"Invalid trigger type at row {line_number}"
            )

        if output_mode not in VALID_OUTPUT_MODES:
            raise CommandError(
                f"Invalid output mode at row {line_number}"
            )

        if not response_text.strip():
            raise CommandError(
                f"Empty response at row {line_number}"
            )

        if not condition_key or len(condition_key) > 100:
            raise CommandError(
                f"Invalid condition key at row {line_number}"
            )

        if (
            not output_order.isdecimal()
            or int(output_order) < 1
        ):
            raise CommandError(
                f"Invalid output order at row {line_number}"
            )

        if next_stage not in {"유지", "2", "3"}:
            raise CommandError(
                f"Invalid next stage at row {line_number}"
            )

        npc_counters[npc_id] += 1

        trigger_id = (
            f"DT-{npc_id}-{npc_counters[npc_id]:03d}"
        )

        prepared.append({
            "trigger_id": trigger_id,
            "npc_id": npc_id,
            "stage": int(stage),
            "trigger_type": trigger_type,
            "output_mode": output_mode,
            "response_text": response_text,
            "condition_key": condition_key,
            "output_order": int(output_order),
            "metadata": {
                "import_source": "case001_1120",
                "source_sha256": checksum,
                "source_line": line_number,
                "source_draft_status": row["draft_status"],
                "source_evidence_ids": row["evidence_ids"],
                "source_next_stage": next_stage,
                "source_tag": row["tag"],
                "source_repeat_variant": row["repeat_variant"],
                "source_basis": row["source_basis"],
                "runtime_enabled": False,
                "condition_approved": False,
            },
        })

    if dict(npc_counters) != EXPECTED_NPC_COUNTS:
        raise CommandError(
            "NPC distribution mismatch"
        )

    return prepared


class Command(BaseCommand):
    help = "Import CASE-001 dialogue triggers (default: Dry Run)"

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
        records = load_dialogue_csv(options["source"])

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

                if set(characters) != set(EXPECTED_NPC_COUNTS):
                    raise CommandError(
                        "Foundation NPCs are incomplete"
                    )

                for record in records:
                    trigger_id = record["trigger_id"]
                    character = characters[record["npc_id"]]

                    expected = {
                        "character": character,
                        "trigger_id": trigger_id,
                        "stage": record["stage"],
                        "trigger_type": record["trigger_type"],
                        "output_mode": record["output_mode"],
                        "response_text": record["response_text"],
                        "condition_key": record["condition_key"],
                        "output_order": record["output_order"],
                        "is_active": False,
                        "metadata": record["metadata"],
                    }

                    item = NPCDialogueTrigger.objects.filter(
                        trigger_id=trigger_id
                    ).first()

                    if item is not None:
                        if (
                            item.character_id != character.pk
                            or item.stage != expected["stage"]
                            or item.trigger_type != expected["trigger_type"]
                            or item.output_mode != expected["output_mode"]
                            or item.response_text != expected["response_text"]
                            or item.condition_key != expected["condition_key"]
                            or item.output_order != expected["output_order"]
                            or item.is_active is not False
                            or item.metadata != expected["metadata"]
                        ):
                            raise CommandError(
                                f"Existing trigger conflict: {trigger_id}"
                            )

                        existing += 1
                        continue

                    item = NPCDialogueTrigger(**expected)
                    item.full_clean()
                    item.save()
                    created += 1

                self.stdout.write(
                    f"Source records: {len(records)}"
                )
                self.stdout.write(
                    f"New triggers: {created}"
                )
                self.stdout.write(
                    f"Existing triggers: {existing}"
                )

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Dialogue import failed: {exc}"
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
