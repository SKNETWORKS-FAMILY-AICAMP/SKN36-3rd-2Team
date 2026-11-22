
"""CASE-001 scene importer.

Default: Dry Run
--apply: Commit transaction
"""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, Chapter, Scene


EXPECTED_SCHEMA = "case001-scenes-2026-11-20"

EXPECTED_CHAPTER_COUNTS = {
    "CH00": 5,
    "CH01": 5,
    "CH02": 6,
    "CH03": 9,
    "CH04": 5,
}

VISIBILITY_MAPPING = {
    "UNLOCKED_ONLY": Scene.Visibility.UNLOCKED_ONLY,
    "ENGINE_ONLY_UNTIL_UNLOCK": Scene.Visibility.ENGINE_ONLY,
}

SOURCE_FIELDS = {
    "scene_id",
    "chapter",
    "title",
    "scene_text",
}


def load_scenes(path: Path):
    """Validate the source before any database operations."""

    try:
        if not path.is_file():
            raise CommandError(f"Source file not found: {path}")

        if path.stat().st_size > 5_000_000:
            raise CommandError("Source file exceeds 5 MB")

        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))

    except (OSError, UnicodeError, ValueError) as exc:
        raise CommandError(
            f"Cannot read scene source: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise CommandError("JSON root must be an object")

    if data.get("schema_version") != EXPECTED_SCHEMA:
        raise CommandError("Unsupported scene schema version")

    if data.get("not_backend_contract") is not True:
        raise CommandError(
            "Scene source contract flag mismatch"
        )

    scenes = data.get("scenes")

    if not isinstance(scenes, list) or len(scenes) != 30:
        raise CommandError("Expected exactly 30 scenes")

    seen_ids = set()
    chapter_counts = Counter()

    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise CommandError(
                f"Scene {index} must be an object"
            )

        scene_id = scene.get("scene_id")
        chapter = scene.get("chapter")
        title = scene.get("title")
        scene_text = scene.get("scene_text")

        if (
            not isinstance(scene_id, str)
            or not re.fullmatch(r"SC-\d{4}", scene_id)
        ):
            raise CommandError(
                f"Invalid scene ID at index {index}"
            )

        if scene_id in seen_ids:
            raise CommandError(
                f"Duplicate scene ID: {scene_id}"
            )

        seen_ids.add(scene_id)

        if chapter not in EXPECTED_CHAPTER_COUNTS:
            raise CommandError(
                f"Invalid chapter: {scene_id}"
            )

        # SC-0201 must belong to CH02.
        if scene_id[3:5] != chapter[2:]:
            raise CommandError(
                f"Scene/chapter mismatch: {scene_id}"
            )

        if not isinstance(title, str) or not title.strip():
            raise CommandError(
                f"Missing scene title: {scene_id}"
            )

        if (
            not isinstance(scene_text, str)
            or not scene_text.strip()
        ):
            raise CommandError(
                f"Missing scene text: {scene_id}"
            )

        if scene.get("visibility") not in VISIBILITY_MAPPING:
            raise CommandError(
                f"Unknown visibility: {scene_id}"
            )

        if scene.get("status") != "CONTENT_FINAL_ENGINE_PENDING":
            raise CommandError(
                f"Unexpected scene status: {scene_id}"
            )

        chapter_counts[chapter] += 1

    if dict(chapter_counts) != EXPECTED_CHAPTER_COUNTS:
        raise CommandError(
            f"Chapter distribution mismatch: {dict(chapter_counts)}"
        )

    return scenes, hashlib.sha256(raw).hexdigest()


class Command(BaseCommand):
    help = "Import CASE-001 scenes with safe visibility defaults"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=Path,
            required=True,
        )

        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit changes; default is Dry Run",
        )

    def handle(self, *args, **options):
        scenes, checksum = load_scenes(options["source"])

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
                        "Scene import requires a DRAFT case"
                    )

                chapters = {
                    chapter.code: chapter
                    for chapter in Chapter.objects.filter(case=case)
                }

                if set(chapters) != set(EXPECTED_CHAPTER_COUNTS):
                    raise CommandError(
                        "Foundation chapters are incomplete"
                    )

                for source in scenes:
                    scene_id = source["scene_id"]
                    chapter = chapters[source["chapter"]]

                    visibility = VISIBILITY_MAPPING[
                        source["visibility"]
                    ]

                    # Preserve proposals without activating them.
                    source_details = {
                        key: value
                        for key, value in source.items()
                        if key not in SOURCE_FIELDS
                    }

                    metadata = {
                        "import_source": "case001_1120",
                        "source_sha256": checksum,
                        "source_visibility": source["visibility"],
                        "source_status": source["status"],
                        "runtime_enabled": False,
                        "backend_contract_approved": False,
                        "source_details": source_details,
                    }

                    expected = {
                        "case": case,
                        "chapter": chapter,
                        "scene_id": scene_id,
                        "title": source["title"].strip(),
                        "scene_text": source["scene_text"],
                        "visibility": visibility,
                        "metadata": metadata,
                    }

                    item = Scene.objects.filter(
                        case=case,
                        scene_id=scene_id,
                    ).first()

                    if item is not None:
                        if (
                            item.chapter_id != chapter.pk
                            or item.title != expected["title"]
                            or item.scene_text != expected["scene_text"]
                            or item.visibility != visibility
                            or item.metadata != metadata
                        ):
                            raise CommandError(
                                f"Existing scene conflict: {scene_id}"
                            )

                        existing += 1
                        continue

                    item = Scene(**expected)
                    item.full_clean()
                    item.save()
                    created += 1

                self.stdout.write(
                    f"Source records: {len(scenes)}"
                )
                self.stdout.write(
                    f"New scenes: {created}"
                )
                self.stdout.write(
                    f"Existing scenes: {existing}"
                )

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Scene import failed: {exc}"
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
