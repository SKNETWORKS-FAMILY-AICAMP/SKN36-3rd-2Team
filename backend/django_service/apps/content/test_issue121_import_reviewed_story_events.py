"""Issue #121: reviewed StoryEvent import integration tests."""

import csv
import io
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.content.access_policy import is_runtime_approved
from apps.content.management.commands.import_reviewed_story_events import (
    COLUMNS,
)
from apps.content.models import Case, Chapter, Evidence, Scene, StoryEvent


class ReviewedStoryEventImportTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.csv_path = Path(self.temp_dir.name) / "review.csv"

        self.case = Case.objects.create(
            case_id="CASE-001",
            title="Issue 121 Test Case",
        )

        self.chapter = Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="Chapter 1",
        )

        Scene.objects.create(
            case=self.case,
            chapter=self.chapter,
            scene_id="SC-0101",
            title="Test Scene",
            scene_text="Synthetic test scene only.",
        )

        Evidence.objects.bulk_create(
            [
                Evidence(
                    case=self.case,
                    evidence_id=f"E{i:02d}",
                    name=f"Test E{i:02d}",
                )
                for i in range(1, 31)
            ]
        )

    def make_rows(self):
        return [
            {
                "create_event": "NO",
                "evidence_id": f"E{i:02d}",
                "evidence_name": f"Test E{i:02d}",
                "holder_character_id": "",
                "required_evidence_ids": "",
                "chapter": "",
                "scene_id": "",
                "event_key": "",
                "event_title": "",
                "event_text": "",
                "review_status": "PENDING",
            }
            for i in range(1, 31)
        ]

    def approve_row(self, rows, index, event_number):
        row = rows[index]
        evidence_id = row["evidence_id"]

        row.update(
            {
                "create_event": "YES",
                "required_evidence_ids": evidence_id,
                "chapter": "CH01",
                "scene_id": "SC-0101",
                "event_key": f"EVT-CH01-{event_number:03d}",
                "event_title": f"Test event {event_number}",
                "event_text": "Synthetic approved review content.",
                "review_status": "REVIEWED",
            }
        )

    def write_rows(self, rows, *, columns=COLUMNS):
        with self.csv_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=columns,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)

    def run_import(self, *, apply=False):
        output = io.StringIO()
        args = ["--source", str(self.csv_path)]

        if apply:
            args.append("--apply")

        call_command(
            "import_reviewed_story_events",
            *args,
            stdout=output,
        )

        return output.getvalue()

    def test_invalid_csv_header_is_rejected(self):
        self.write_rows(
            self.make_rows(),
            columns=("evidence_id",),
        )

        with self.assertRaises(CommandError):
            self.run_import()

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_duplicate_evidence_id_is_rejected(self):
        rows = self.make_rows()
        rows[29]["evidence_id"] = "E29"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import()

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_unreviewed_event_is_rejected(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        rows[0]["review_status"] = "PENDING"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import()

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_invalid_required_evidence_is_rejected(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        rows[0]["required_evidence_ids"] = "E02"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import()

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_dry_run_does_not_commit(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        self.write_rows(rows)

        output = self.run_import()

        self.assertIn("DRY RUN", output)
        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_apply_creates_unpublished_event(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        self.write_rows(rows)

        output = self.run_import(apply=True)

        self.assertIn("IMPORT COMMITTED", output)
        self.assertEqual(StoryEvent.objects.count(), 1)

        event = StoryEvent.objects.get(
            event_key="EVT-CH01-001",
        )

        self.assertEqual(
            event.conditions["requiredEvidenceIds"],
            ["E01"],
        )
        self.assertFalse(event.metadata["runtime_enabled"])
        self.assertFalse(
            event.metadata["backend_contract_approved"]
        )
        self.assertFalse(is_runtime_approved(event))

    def test_repeated_apply_is_idempotent(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        self.write_rows(rows)

        self.run_import(apply=True)
        output = self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 1)
        self.assertIn("Existing events: 1", output)

    def test_conflict_rolls_back_previous_inserts(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        self.approve_row(rows, 1, 2)
        self.write_rows(rows)

        # Pre-existing conflicting record ensures that the second
        # insert fails after the first insert is attempted.
        StoryEvent.objects.create(
            chapter=self.chapter,
            event_key="EVT-CH01-002",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={"requiredEvidenceIds": ["E02"]},
            payload={
                "title": "Conflicting content",
                "text": "Must remain unchanged.",
            },
            metadata={"existing": True},
        )

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertFalse(
            StoryEvent.objects.filter(
                event_key="EVT-CH01-001",
            ).exists()
        )

        self.assertEqual(StoryEvent.objects.count(), 1)
        self.assertEqual(
            StoryEvent.objects.get(
                event_key="EVT-CH01-002",
            ).metadata,
            {"existing": True},
        )

    def test_non_draft_case_is_rejected(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        self.write_rows(rows)

        self.case.status = Case.Status.PUBLISHED
        self.case.save(update_fields=["status"])

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_missing_scene_is_rejected(self):
        rows = self.make_rows()
        self.approve_row(rows, 0, 1)
        rows[0]["scene_id"] = "SC-0102"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)
