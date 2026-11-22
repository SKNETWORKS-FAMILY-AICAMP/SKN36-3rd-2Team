
"""CASE-001 NPC knowledge/smalltalk card importer."""

import csv
import hashlib
import io
import re
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, Character, NPCCard


SOURCES = {
    "08_NPC_KNOWLEDGE_CARDS.csv": {
        "type": NPCCard.CardType.KNOWLEDGE,
        "count": 100,
        "content_field": "내용",
        "pattern": r"^K-C(0[1-9]|10)-[0-9]{2}$",
    },
    "08_NPC_SMALLTALK_CARDS.csv": {
        "type": NPCCard.CardType.SMALLTALK,
        "count": 40,
        "content_field": "알고있는사실",
        "pattern": r"^K-C(0[1-9]|10)-S[0-9]{2}$",
    },
}

NPC_IDS = {f"C{i:02d}" for i in range(1, 11)}


def load_cards(source_dir: Path):
    """Validate both CSV files before database writes."""
    if not source_dir.is_dir():
        raise CommandError(
            f"Source directory not found: {source_dir}"
        )

    cards = []
    seen_ids = set()

    for filename, config in SOURCES.items():
        path = source_dir / filename

        try:
            if not path.is_file():
                raise CommandError(f"Missing source: {filename}")

            if path.stat().st_size > 5_000_000:
                raise CommandError(f"Source too large: {filename}")

            raw = path.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()

            reader = csv.DictReader(
                io.StringIO(raw.decode("utf-8-sig"))
            )
            columns = reader.fieldnames or []

            if len(columns) != len(set(columns)):
                raise CommandError(
                    f"Duplicate columns: {filename}"
                )

            required = {
                "npc_id",
                "card_id",
                config["content_field"],
                "공개조건",
            }

            if not required.issubset(columns):
                raise CommandError(
                    f"Missing columns in {filename}: "
                    f"{sorted(required - set(columns))}"
                )

            rows = list(reader)

        except (OSError, UnicodeError, csv.Error) as exc:
            raise CommandError(
                f"Cannot read {filename}: {exc}"
            ) from exc

        if len(rows) != config["count"]:
            raise CommandError(
                f"Unexpected row count in {filename}: "
                f"{len(rows)}"
            )

        for line_number, row in enumerate(rows, start=2):
            if None in row or any(
                value is None for value in row.values()
            ):
                raise CommandError(
                    f"Malformed CSV row: {filename}:{line_number}"
                )

            npc_id = row["npc_id"].strip()
            card_id = row["card_id"].strip()
            content = row[config["content_field"]].strip()
            disclosure = row["공개조건"].strip()

            if npc_id not in NPC_IDS:
                raise CommandError(
                    f"Unknown NPC: {npc_id}"
                )

            if not re.fullmatch(config["pattern"], card_id):
                raise CommandError(
                    f"Invalid card ID: {card_id}"
                )

            if not card_id.startswith(f"K-{npc_id}-"):
                raise CommandError(
                    f"NPC/card mismatch: {card_id}"
                )

            if card_id in seen_ids:
                raise CommandError(
                    f"Duplicate card ID: {card_id}"
                )

            if not content:
                raise CommandError(
                    f"Empty content: {card_id}"
                )

            if not disclosure:
                raise CommandError(
                    f"Empty disclosure condition: {card_id}"
                )

            seen_ids.add(card_id)

            # No disclosure condition is approved at import time.
            policy = {
                "status": "UNRESOLVED",
                "allow": False,
                "source_condition": disclosure,
            }

            metadata = {
                "import_source": "case001_1120",
                "source_file": filename,
                "source_sha256": checksum,
                "runtime_enabled": False,
                "source_row": dict(row),
            }

            cards.append({
                "npc_id": npc_id,
                "card_id": card_id,
                "card_type": config["type"],
                "content": content,
                "disclosure_policy": policy,
                "metadata": metadata,
            })

    if len(cards) != 140 or len(seen_ids) != 140:
        raise CommandError("Card count validation failed")

    return cards


class Command(BaseCommand):
    help = "Import CASE-001 NPC cards with deny-by-default policy"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            required=True,
            type=Path,
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit changes; default is Dry Run",
        )

    def handle(self, *args, **options):
        cards = load_cards(options["source_dir"])

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
                    item.character_id: item
                    for item in Character.objects.filter(case=case)
                }

                if set(characters) != NPC_IDS:
                    raise CommandError(
                        "Foundation NPCs are incomplete"
                    )

                for source in cards:
                    character = characters[source["npc_id"]]
                    card_id = source["card_id"]

                    expected = {
                        "character": character,
                        "card_id": card_id,
                        "card_type": source["card_type"],
                        "content": source["content"],
                        "disclosure_policy": source["disclosure_policy"],
                        "metadata": source["metadata"],
                    }

                    card = NPCCard.objects.filter(
                        character=character,
                        card_id=card_id,
                    ).first()

                    if card is not None:
                        if (
                            card.card_type != expected["card_type"]
                            or card.content != expected["content"]
                            or card.disclosure_policy
                            != expected["disclosure_policy"]
                            or card.metadata != expected["metadata"]
                        ):
                            raise CommandError(
                                f"Existing card conflict: {card_id}"
                            )

                        existing += 1
                        continue

                    card = NPCCard(**expected)
                    card.full_clean()
                    card.save()
                    created += 1

                self.stdout.write(
                    f"Source records: {len(cards)}"
                )
                self.stdout.write(
                    f"New cards: {created}"
                )
                self.stdout.write(
                    f"Existing cards: {existing}"
                )

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"NPC card import failed: {exc}"
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
