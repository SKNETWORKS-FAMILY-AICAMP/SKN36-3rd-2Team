
"""CASE-001 Objective Import.

기본 실행은 Dry Run입니다.
미승인 완료 규칙은 실행하지 않습니다.
"""

import csv
import hashlib
import io
import re
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, Chapter, Evidence, Objective


EXPECTED_COUNT = 25

EXPECTED_CHAPTERS = {
    "CH00": 2,
    "CH01": 5,
    "CH02": 8,
    "CH03": 7,
    "CH04": 3,
}

REQUIRED_COLUMNS = {
    "objective_id",
    "unlocked_by_evidence",
    "target_evidence",
    "chapter",
    "player_goal",
    "trigger_source",
    "hint_1",
    "hint_2",
    "hint_3",
    "wrong_feedback",
    "completion",
    "status",
}

OBJECTIVE_ID_PATTERN = re.compile(
    r"^OBJ_(?:\d{3}|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)$"
)

EVIDENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])E\d{2}(?![A-Za-z0-9])"
)

SPECIAL_TARGETS = {"FINAL", "DEEP"}


def extract_evidence_ids(value, *, line_number, field):
    """원본 문자열에서 참조 ID만 확인하고 원문은 보존합니다."""
    if not value:
        return set()

    ids = set(EVIDENCE_PATTERN.findall(value))

    if not ids:
        raise CommandError(
            f"Row {line_number}: unrecognized {field}"
        )

    return ids


def load_objectives(path):
    """CSV 형식, 건수, 식별자와 필수 값을 검증합니다."""
    try:
        if not path.is_file():
            raise CommandError(f"Source not found: {path}")

        if path.stat().st_size > 1_000_000:
            raise CommandError("Source exceeds 1 MB")

        raw = path.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()

        reader = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig"), newline=""),
            strict=True,
        )

        columns = reader.fieldnames or []

        if (
            len(columns) != len(set(columns))
            or set(columns) != REQUIRED_COLUMNS
        ):
            raise CommandError("Invalid CSV columns")

        rows = list(reader)

    except (OSError, UnicodeError, csv.Error) as exc:
        raise CommandError(
            f"Unable to read Objective CSV: {exc}"
        ) from exc

    if len(rows) != EXPECTED_COUNT:
        raise CommandError(
            f"Expected {EXPECTED_COUNT} rows, found {len(rows)}"
        )

    prepared = []
    seen_ids = set()
    chapter_counts = Counter()
    referenced_evidence = set()
    special_targets = Counter()

    for line_number, row in enumerate(rows, start=2):
        if (
            None in row
            or any(value is None for value in row.values())
        ):
            raise CommandError(
                f"Malformed row: {line_number}"
            )

        values = {
            key: value.strip()
            for key, value in row.items()
        }

        objective_id = values["objective_id"]
        chapter_code = values["chapter"]
        unlock = values["unlocked_by_evidence"]
        target = values["target_evidence"]

        if (
            len(objective_id) > 64
            or not OBJECTIVE_ID_PATTERN.fullmatch(objective_id)
        ):
            raise CommandError(
                f"Invalid Objective ID at row {line_number}"
            )

        if objective_id in seen_ids:
            raise CommandError(
                f"Duplicate Objective ID: {objective_id}"
            )

        seen_ids.add(objective_id)

        if chapter_code not in EXPECTED_CHAPTERS:
            raise CommandError(
                f"Unknown chapter at row {line_number}"
            )

        chapter_counts[chapter_code] += 1

        if not values["player_goal"]:
            raise CommandError(
                f"Empty player goal at row {line_number}"
            )

        hints = [
            values[f"hint_{number}"]
            for number in range(1, 4)
        ]

        if any(not hint for hint in hints):
            raise CommandError(
                f"Incomplete hints at row {line_number}"
            )

        for field in (
            "trigger_source",
            "wrong_feedback",
            "completion",
            "status",
        ):
            if not values[field]:
                raise CommandError(
                    f"Missing {field} at row {line_number}"
                )

        referenced_evidence.update(
            extract_evidence_ids(
                unlock,
                line_number=line_number,
                field="unlocked_by_evidence",
            )
        )

        if target in SPECIAL_TARGETS:
            target_type = "symbolic"
            special_targets[target] += 1
        elif target:
            target_type = "evidence"
            referenced_evidence.update(
                extract_evidence_ids(
                    target,
                    line_number=line_number,
                    field="target_evidence",
                )
            )
        else:
            target_type = "none"

        prepared.append({
            "objective_id": objective_id,
            "chapter_code": chapter_code,
            "player_goal": values["player_goal"],
            "hints": hints,
            "metadata": {
                "import_source": "case001_1120",
                "source_sha256": source_hash,
                "source_line": line_number,
                "source_unlocked_by_evidence": unlock,
                "source_target_evidence": target,
                "source_target_type": target_type,
                "source_trigger_source": values["trigger_source"],
                "source_wrong_feedback": values["wrong_feedback"],
                "source_completion": values["completion"],
                "source_status": values["status"],
                "runtime_enabled": False,
                "completion_rule_approved": False,
            },
        })

    if dict(chapter_counts) != EXPECTED_CHAPTERS:
        raise CommandError(
            "Objective chapter distribution mismatch"
        )

    if dict(special_targets) != {"FINAL": 1, "DEEP": 1}:
        raise CommandError(
            "Expected one FINAL and one DEEP target"
        )

    return prepared, referenced_evidence


class Command(BaseCommand):
    help = "Import CASE-001 Objectives (Dry Run by default)"

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
        records, referenced_ids = load_objectives(
            options["source"]
        )

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

                chapters = {
                    chapter.code: chapter
                    for chapter in Chapter.objects.filter(
                        case=case
                    )
                }

                if set(chapters) != set(EXPECTED_CHAPTERS):
                    raise CommandError(
                        "Foundation chapters are incomplete"
                    )

                evidence_ids = set(
                    Evidence.objects.filter(case=case)
                    .values_list("evidence_id", flat=True)
                )

                missing = referenced_ids - evidence_ids

                if missing:
                    raise CommandError(
                        f"Unknown evidence: {sorted(missing)}"
                    )

                # 사건 내 Objective ID 충돌 여부를 먼저 검사합니다.
                imported_ids = {
                    record["objective_id"]
                    for record in records
                }

                existing_by_id = {}

                stored = Objective.objects.filter(
                    chapter__case=case,
                    objective_id__in=imported_ids,
                )

                for item in stored:
                    if item.objective_id in existing_by_id:
                        raise CommandError(
                            "Duplicate existing Objective ID: "
                            f"{item.objective_id}"
                        )

                    existing_by_id[item.objective_id] = item

                for record in records:
                    objective_id = record["objective_id"]
                    chapter = chapters[record["chapter_code"]]

                    expected = {
                        "chapter": chapter,
                        "objective_id": objective_id,
                        "player_goal": record["player_goal"],
                        "hints": record["hints"],
                        "completion_rule": {},
                        "is_active": False,
                        "metadata": record["metadata"],
                    }

                    item = existing_by_id.get(objective_id)

                    if item is not None:
                        if (
                            item.chapter_id != chapter.pk
                            or item.player_goal != expected["player_goal"]
                            or item.hints != expected["hints"]
                            or item.completion_rule != {}
                            or item.is_active is not False
                            or item.metadata != expected["metadata"]
                        ):
                            raise CommandError(
                                f"Existing Objective conflict: {objective_id}"
                            )

                        existing += 1
                        continue

                    objective = Objective(**expected)
                    objective.full_clean()
                    objective.save()
                    created += 1

                self.stdout.write(
                    f"Source records: {len(records)}"
                )
                self.stdout.write(
                    f"New objectives: {created}"
                )
                self.stdout.write(
                    f"Existing objectives: {existing}"
                )

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Objective import failed: {exc}"
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
