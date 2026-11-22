"""Import reviewed CASE-001 story events from V3 mapping."""

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, EvidenceLink, Scene, StoryEvent


FIELDS = (
    "source_story_id",
    "source_scene_id",
    "chapter",
    "scene_title",
    "metadata_reference_paths",
    "related_evidence_ids",
    "inference_ids",
    "presentation_modes",
    "create_event",
    "review_status",
    "event_key",
    "required_evidence_ids",
    "event_title",
    "event_text",
)

STORY_RE = re.compile(r"STORY_[0-9]{3}")
EVIDENCE_RE = re.compile(r"E(?:0[1-9]|[12][0-9]|30)")
EVENT_RE = re.compile(r"EVT-CH0[0-4]-[0-9]{3}")

VALID_MODES = {
    "\uB2E8\uB3C5",
    "\uBCF5\uC218(2\uAC1C)",
    "\uBCF5\uC218(3\uAC1C)",
}


def load_rows(path):
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise CommandError("Missing or oversized mapping CSV")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            if tuple(reader.fieldnames or ()) != FIELDS:
                raise CommandError("Unexpected CSV columns")

            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CommandError("Unable to parse CSV") from exc

    if len(rows) != 15:
        raise CommandError("Expected exactly 15 story rows")

    cleaned = []

    for number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise CommandError(f"Malformed CSV row {number}")

        row = {key: value.strip() for key, value in row.items()}

        if (
            row["create_event"] not in {"YES", "NO"}
            or row["review_status"] not in {"PENDING", "REVIEWED"}
        ):
            raise CommandError(f"Invalid review state at row {number}")

        if (
            row["create_event"] == "YES"
            and row["review_status"] != "REVIEWED"
        ):
            raise CommandError(f"Unreviewed event at row {number}")

        cleaned.append(row)

    story_ids = [row["source_story_id"] for row in cleaned]

    if (
        len(set(story_ids)) != 15
        or any(not STORY_RE.fullmatch(value) for value in story_ids)
    ):
        raise CommandError("Invalid or duplicate source story IDs")

    return cleaned


def normalize_mode(value):
    if not isinstance(value, str):
        raise CommandError("Invalid presentation mode type")

    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", "", normalized)

    if normalized not in VALID_MODES:
        raise CommandError("Unrecognized presentation mode")

    return normalized


def contains_story_reference(metadata, story_id):
    if not isinstance(metadata, dict):
        return False

    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(story_id)}(?![A-Za-z0-9_])"
    )

    content = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    return bool(pattern.search(content))


class Command(BaseCommand):
    help = "Import reviewed STORY-based events (dry run by default)"

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        rows = load_rows(options["source"])
        created = 0
        existing = 0
        selected_keys = set()

        try:
            with transaction.atomic():
                case = Case.objects.filter(case_id="CASE-001").first()

                if case is None or case.status != Case.Status.DRAFT:
                    raise CommandError("CASE-001 must exist and be DRAFT")

                links = list(
                    EvidenceLink.objects.filter(
                        from_evidence__case=case,
                        to_evidence__case=case,
                    ).select_related("from_evidence", "to_evidence")
                )

                scenes = list(
                    Scene.objects.filter(case=case)
                    .select_related("chapter")
                )

                if len(links) != 23 or len(scenes) != 30:
                    raise CommandError("Source inventory has changed")

                links_by_story = defaultdict(list)

                for link in links:
                    if (
                        not isinstance(link.metadata, dict)
                        or link.is_active
                        or not link.needs_canon_approval
                    ):
                        raise CommandError("Evidence link approval mismatch")

                    story_id = link.metadata.get("source_unlock_event")

                    if not isinstance(story_id, str) or not STORY_RE.fullmatch(story_id):
                        raise CommandError("Invalid source story reference")

                    links_by_story[story_id].append(link)

                if set(links_by_story) != {
                    row["source_story_id"] for row in rows
                }:
                    raise CommandError("Story inventory mismatch")

                for row in rows:
                    story_id = row["source_story_id"]
                    related = links_by_story[story_id]

                    actual_evidence = {
                        evidence_id
                        for link in related
                        for evidence_id in (
                            link.from_evidence.evidence_id,
                            link.to_evidence.evidence_id,
                        )
                    }

                    actual_inferences = {
                        link.resulting_inference for link in related
                    }

                    actual_modes = {
                        normalize_mode(
                            link.metadata.get("source_presentation_mode")
                        )
                        for link in related
                    }

                    if (
                        "|".join(sorted(actual_evidence))
                        != row["related_evidence_ids"]
                        or "|".join(sorted(actual_inferences))
                        != row["inference_ids"]
                        or "|".join(sorted(actual_modes))
                        != row["presentation_modes"]
                    ):
                        raise CommandError(
                            f"Source evidence mapping changed: {story_id}"
                        )

                    matching_scenes = [
                        scene for scene in scenes
                        if contains_story_reference(scene.metadata, story_id)
                    ]

                    if len(matching_scenes) != 1:
                        raise CommandError(
                            f"Ambiguous scene mapping: {story_id}"
                        )

                    scene = matching_scenes[0]

                    if (
                        scene.scene_id != row["source_scene_id"]
                        or scene.chapter.code != row["chapter"]
                        or scene.title != row["scene_title"]
                        or not row["metadata_reference_paths"]
                    ):
                        raise CommandError(
                            f"Scene mapping changed: {story_id}"
                        )

                    if row["create_event"] != "YES":
                        continue

                    # Deep-ending evidence rules require a separate gate.
                    if any(link.relationship == "deep_gate" for link in related):
                        raise CommandError(
                            f"Deep-gate story requires separate review: {story_id}"
                        )

                    event_key = row["event_key"]

                    if (
                        not EVENT_RE.fullmatch(event_key)
                        or not event_key.startswith(
                            f"EVT-{scene.chapter.code}-"
                        )
                        or event_key in selected_keys
                    ):
                        raise CommandError(
                            f"Invalid or duplicate event key: {event_key}"
                        )

                    selected_keys.add(event_key)

                    required = row["required_evidence_ids"].split("|")

                    if (
                        not required
                        or len(required) != len(set(required))
                        or any(
                            not EVIDENCE_RE.fullmatch(value)
                            for value in required
                        )
                        or not set(required).issubset(actual_evidence)
                    ):
                        raise CommandError(
                            f"Invalid evidence gate: {story_id}"
                        )

                    if (
                        not 1 <= len(row["event_title"]) <= 120
                        or not 1 <= len(row["event_text"]) <= 5000
                    ):
                        raise CommandError(
                            f"Invalid event content: {story_id}"
                        )

                    expected = {
                        "chapter": scene.chapter,
                        "trigger_type": (
                            StoryEvent.TriggerType.EVIDENCE_COLLECTED
                        ),
                        "conditions": {
                            "requiredEvidenceIds": required,
                        },
                        "payload": {
                            "title": row["event_title"],
                            "text": row["event_text"],
                        },
                        "metadata": {
                            "source_story_id": story_id,
                            "source_scene_id": scene.scene_id,
                            "review_status": "REVIEWED",
                            "runtime_enabled": False,
                            "backend_contract_approved": False,
                        },
                    }

                    event = StoryEvent.objects.filter(
                        event_key=event_key
                    ).first()

                    if event is not None:
                        if any(
                            getattr(event, field) != value
                            for field, value in expected.items()
                        ):
                            raise CommandError(
                                f"Existing event conflict: {event_key}"
                            )

                        existing += 1
                        continue

                    event = StoryEvent(
                        event_key=event_key,
                        **expected,
                    )
                    event.full_clean()
                    event.save()
                    created += 1

                self.stdout.write(
                    f"Story candidates: {len(rows)}"
                )
                self.stdout.write(
                    f"Selected events: {len(selected_keys)}"
                )
                self.stdout.write(f"New events: {created}")
                self.stdout.write(f"Existing events: {existing}")

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError("Event validation failed") from exc

        if options["apply"]:
            self.stdout.write(self.style.SUCCESS("IMPORT COMMITTED"))
        else:
            self.stdout.write(
                self.style.WARNING("DRY RUN - NO CHANGES COMMITTED")
            )
