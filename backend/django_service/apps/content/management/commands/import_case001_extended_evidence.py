
"""CASE-001 E11~E30 evidence importer."""

import csv
import hashlib
import io
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, Chapter, Character, Evidence


EXPECTED_IDS = {f"E{i:02d}" for i in range(11, 31)}

REQUIRED_COLUMNS = {
    "evidence_id",
    "title",
    "holder_npc_id",
    "chapter",
    "score_points",
    "access_scope",
    "canon_status",
}


def load_evidence_csv(path: Path):
    """Parse and validate source data before opening a DB transaction."""
    if not path.is_file():
        raise CommandError(f"CSV file not found: {path}")

    if path.stat().st_size > 5_000_000:
        raise CommandError("CSV file exceeds size limit")

    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()

    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        columns = reader.fieldnames or []

        if len(columns) != len(set(columns)):
            raise CommandError("Duplicate CSV columns")

        missing = REQUIRED_COLUMNS - set(columns)

        if missing:
            raise CommandError(
                f"Missing CSV columns: {sorted(missing)}"
            )

        rows = list(reader)

    except (UnicodeError, csv.Error) as exc:
        raise CommandError(f"Invalid CSV: {exc}") from exc

    seen = set()

    for index, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise CommandError(f"Malformed CSV row: {index}")

        evidence_id = row["evidence_id"].strip()

        if evidence_id in seen:
            raise CommandError(f"Duplicate evidence ID: {evidence_id}")

        seen.add(evidence_id)

        if evidence_id not in EXPECTED_IDS:
            raise CommandError(f"Unexpected evidence ID: {evidence_id}")

        if not row["title"].strip():
            raise CommandError(f"Missing title: {evidence_id}")

        if row["score_points"].strip() != "미정(백엔드)":
            raise CommandError(
                f"Unexpected score policy: {evidence_id}"
            )

        if row["access_scope"].strip() != "UNLOCKED_ONLY":
            raise CommandError(
                f"Unexpected access scope: {evidence_id}"
            )

        if not row["canon_status"].strip():
            raise CommandError(
                f"Missing canon status: {evidence_id}"
            )

        if row["chapter"].strip() not in {
            "CH01", "CH02", "CH03", "CH04"
        }:
            raise CommandError(
                f"Invalid chapter: {evidence_id}"
            )

    if seen != EXPECTED_IDS:
        raise CommandError(
            f"Evidence ID mismatch; missing={sorted(EXPECTED_IDS - seen)}"
        )

    return rows, checksum


class Command(BaseCommand):
    help = "Import CASE-001 E11~E30 evidence in a fail-closed manner"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=Path,
            required=True,
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit changes; otherwise rollback.",
        )

    def handle(self, *args, **options):
        try:
            rows, checksum = load_evidence_csv(options["source"])
        except OSError as exc:
            raise CommandError(f"Cannot read source: {exc}") from exc

        created = 0
        existing = 0

        try:
            with transaction.atomic():
                case = Case.objects.filter(
                    case_id="CASE-001"
                ).first()

                if case is None:
                    raise CommandError(
                        "CASE-001 is missing. Import foundation first."
                    )

                if case.status != Case.Status.DRAFT:
                    raise CommandError(
                        "Import is allowed only for a DRAFT case"
                    )

                chapters = set(
                    Chapter.objects.filter(case=case)
                    .values_list("code", flat=True)
                )

                characters = {
                    npc.character_id: npc
                    for npc in Character.objects.filter(case=case)
                }

                if chapters != {
                    "CH00", "CH01", "CH02", "CH03", "CH04"
                }:
                    raise CommandError("Foundation chapters are incomplete")

                for row in rows:
                    evidence_id = row["evidence_id"].strip()
                    chapter_code = row["chapter"].strip()
                    holder_id = row["holder_npc_id"].strip()

                    if holder_id and holder_id not in characters:
                        raise CommandError(
                            f"Unknown holder: {evidence_id}"
                        )

                    holder = (
                        characters[holder_id] if holder_id else None
                    )

                    # Internal metadata must never be exposed in player APIs.
                    metadata = {
                        "import_source": "case001_1120",
                        "source_sha256": checksum,
                        "source_chapter": chapter_code,
                        "source_access_scope": row["access_scope"].strip(),
                        "source_canon_status": row["canon_status"].strip(),
                        "score_status": "UNDEFINED",
                        "runtime_enabled": False,
                        "internal_source_row": dict(row),
                    }

                    expected_name = row["title"].strip()

                    existing_item = Evidence.objects.filter(
                        case=case,
                        evidence_id=evidence_id,
                    ).first()

                    if existing_item is not None:
                        if (
                            existing_item.name != expected_name
                            or existing_item.holder_id != (
                                holder.pk if holder else None
                            )
                            or existing_item.score is not None
                            or existing_item.metadata != metadata
                        ):
                            raise CommandError(
                                f"Existing evidence conflict: {evidence_id}"
                            )

                        existing += 1
                        continue

                    item = Evidence(
                        case=case,
                        evidence_id=evidence_id,
                        name=expected_name,
                        holder=holder,
                        score=None,
                        metadata=metadata,
                    )
                    item.full_clean()
                    item.save()
                    created += 1

                self.stdout.write(f"Source records: {len(rows)}")
                self.stdout.write(f"New evidence: {created}")
                self.stdout.write(f"Existing evidence: {existing}")

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Evidence import failed: {exc}"
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
