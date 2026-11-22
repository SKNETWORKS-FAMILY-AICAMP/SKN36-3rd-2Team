
"""Import CASE-001 evidence inference links."""

import csv
import hashlib
import io
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, Evidence, EvidenceLink


EXPECTED_COUNT = 23

REQUIRED_COLUMNS = {
    "from_evidence",
    "to_evidence",
    "relationship",
    "resulting_inference",
    "unlock_event",
    "needs_canon_approval",
    "presentation_mode",
    "note",
}

VALID_PRESENTATION_MODES = {
    "단독",
    "복수(2개)",
    "복수(3개)",
}


def load_evidence_links(path: Path):
    """CSV 구조와 증거 관계를 검증합니다."""

    if not path.is_file():
        raise CommandError(f"Source not found: {path}")

    try:
        if path.stat().st_size > 1_000_000:
            raise CommandError("Source exceeds 1 MB")

        raw = path.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()

        reader = csv.DictReader(
            io.StringIO(
                raw.decode("utf-8-sig"),
                newline="",
            )
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

    records = []
    relation_keys = set()
    referenced_ids = set()

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

        source_id = values["from_evidence"]
        target_id = values["to_evidence"]
        relationship = values["relationship"]
        inference = values["resulting_inference"]

        if (
            not source_id
            or not target_id
            or not relationship
            or not inference
        ):
            raise CommandError(
                f"Missing required value at row {line_number}"
            )

        if source_id == target_id:
            raise CommandError(
                f"Self-reference at row {line_number}"
            )

        if len(relationship) > 100:
            raise CommandError(
                f"Relationship too long at row {line_number}"
            )

        if len(inference) > 100:
            raise CommandError(
                f"Inference too long at row {line_number}"
            )

        if not values["unlock_event"]:
            raise CommandError(
                f"Missing unlock event at row {line_number}"
            )

        if values["needs_canon_approval"] != "YES":
            raise CommandError(
                f"Unexpected approval value at row {line_number}"
            )

        if (
            values["presentation_mode"]
            not in VALID_PRESENTATION_MODES
        ):
            raise CommandError(
                f"Invalid presentation mode at row {line_number}"
            )

        relation_key = (
            source_id,
            target_id,
            relationship,
        )

        if relation_key in relation_keys:
            raise CommandError(
                f"Duplicate relationship at row {line_number}"
            )

        relation_keys.add(relation_key)
        referenced_ids.update((source_id, target_id))

        records.append({
            "from_id": source_id,
            "to_id": target_id,
            "relationship": relationship,
            "resulting_inference": inference,
            "metadata": {
                "import_source": "case001_1120",
                "source_sha256": source_hash,
                "source_line": line_number,
                "source_unlock_event": values["unlock_event"],
                "source_presentation_mode": (
                    values["presentation_mode"]
                ),
                "source_needs_canon_approval": "YES",
                "source_note": values["note"],
                "runtime_enabled": False,
                "canon_approved": False,
            },
        })

    return records, referenced_ids


class Command(BaseCommand):
    help = "Import CASE-001 evidence links (Dry Run by default)"

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
        records, referenced_ids = load_evidence_links(
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

                evidences = {
                    obj.evidence_id: obj
                    for obj in Evidence.objects.filter(
                        case=case,
                        evidence_id__in=referenced_ids,
                    )
                }

                missing = referenced_ids - set(evidences)

                if missing:
                    raise CommandError(
                        f"Missing evidence: {sorted(missing)}"
                    )

                for record in records:
                    source = evidences[record["from_id"]]
                    target = evidences[record["to_id"]]

                    expected = {
                        "from_evidence": source,
                        "to_evidence": target,
                        "relationship": record["relationship"],
                        "resulting_inference": (
                            record["resulting_inference"]
                        ),
                        "needs_canon_approval": True,
                        "is_active": False,
                        "metadata": record["metadata"],
                    }

                    item = EvidenceLink.objects.filter(
                        from_evidence=source,
                        to_evidence=target,
                        relationship=record["relationship"],
                    ).first()

                    if item is not None:
                        if (
                            item.resulting_inference
                            != expected["resulting_inference"]
                            or item.needs_canon_approval is not True
                            or item.is_active is not False
                            or item.metadata != expected["metadata"]
                        ):
                            raise CommandError(
                                "Existing evidence link conflict: "
                                f"{record['from_id']} -> "
                                f"{record['to_id']}"
                            )

                        existing += 1
                        continue

                    item = EvidenceLink(**expected)
                    item.full_clean()
                    item.save()
                    created += 1

                self.stdout.write(
                    f"Source records: {len(records)}"
                )
                self.stdout.write(
                    f"New links: {created}"
                )
                self.stdout.write(
                    f"Existing links: {existing}"
                )

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Evidence link import failed: {exc}"
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
