"""Issue #121: CASE-001 V3 StoryEvent importer integration tests."""

import csv
import io
import tempfile
from collections import defaultdict
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.content.access_policy import is_runtime_approved
from apps.content.management.commands.import_case001_story_events_v3 import (
    FIELDS,
)
from apps.content.models import (
    Case,
    Chapter,
    Evidence,
    EvidenceLink,
    Scene,
    StoryEvent,
)


class StoryEventV3ImportTests(TestCase):
    """Test the real importer against a synthetic 30/23/15 inventory."""

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.csv_path = Path(
            self.temporary_directory.name
        ) / "story_mapping.csv"

        self.case = Case.objects.create(
            case_id="CASE-001",
            title="Synthetic integration test",
        )

        self.chapter = Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="Test chapter",
        )

        Evidence.objects.bulk_create(
            [
                Evidence(
                    case=self.case,
                    evidence_id=f"E{i:02d}",
                    name=f"Evidence {i:02d}",
                )
                for i in range(1, 31)
            ]
        )

        self.evidence = {
            item.evidence_id: item
            for item in Evidence.objects.filter(case=self.case)
        }

        self.scenes = {}
        self.links = defaultdict(list)

        # Exactly 30 scenes; 15 scenes have one source STORY reference.
        for i in range(1, 31):
            story_id = f"STORY_{i:03d}" if i <= 15 else None

            metadata = (
                {"source_details": {"result_events": [story_id]}}
                if story_id
                else {}
            )

            scene = Scene.objects.create(
                case=self.case,
                chapter=self.chapter,
                scene_id=f"SC-{100 + i:04d}",
                title=f"Synthetic scene {i}",
                scene_text="Synthetic test data only.",
                metadata=metadata,
            )

            if story_id:
                self.scenes[story_id] = scene

        # One link per STORY: 15 links.
        for i in range(1, 16):
            self.create_link(
                story_id=f"STORY_{i:03d}",
                from_id=f"E{i:02d}",
                to_id=f"E{i + 15:02d}",
                inference=f"INF_{i:03d}",
            )

        # Eight additional relationships: total 23 links.
        for i in range(1, 9):
            self.create_link(
                story_id=f"STORY_{i:03d}",
                from_id=f"E{i:02d}",
                to_id=f"E{i + 16:02d}",
                inference=f"INF_EXTRA_{i:03d}",
            )

        self.assertEqual(Scene.objects.count(), 30)
        self.assertEqual(EvidenceLink.objects.count(), 23)
        self.assertEqual(len(self.scenes), 15)

    def create_link(self, *, story_id, from_id, to_id, inference):
        link = EvidenceLink.objects.create(
            from_evidence=self.evidence[from_id],
            to_evidence=self.evidence[to_id],
            relationship="supports",
            resulting_inference=inference,
            needs_canon_approval=True,
            is_active=False,
            metadata={
                "source_unlock_event": story_id,
                "source_presentation_mode": "단독",
            },
        )
        self.links[story_id].append(link)

    def make_rows(self):
        rows = []

        for i in range(1, 16):
            story_id = f"STORY_{i:03d}"
            scene = self.scenes[story_id]
            links = self.links[story_id]

            related_evidence = {
                evidence_id
                for link in links
                for evidence_id in (
                    link.from_evidence.evidence_id,
                    link.to_evidence.evidence_id,
                )
            }

            rows.append(
                {
                    "source_story_id": story_id,
                    "source_scene_id": scene.scene_id,
                    "chapter": "CH01",
                    "scene_title": scene.title,
                    "metadata_reference_paths": (
                        "source_details.result_events"
                    ),
                    "related_evidence_ids": "|".join(
                        sorted(related_evidence)
                    ),
                    "inference_ids": "|".join(
                        sorted(
                            link.resulting_inference
                            for link in links
                        )
                    ),
                    "presentation_modes": "단독",
                    "create_event": "NO",
                    "review_status": "PENDING",
                    "event_key": "",
                    "required_evidence_ids": "",
                    "event_title": "",
                    "event_text": "",
                }
            )

        return rows

    @staticmethod
    def select_event(rows, number):
        row = rows[number - 1]

        row.update(
            {
                "create_event": "YES",
                "review_status": "REVIEWED",
                "event_key": f"EVT-CH01-{number:03d}",
                "required_evidence_ids": f"E{number:02d}",
                "event_title": f"Synthetic event {number}",
                "event_text": (
                    "Synthetic content, not a real scenario."
                ),
            }
        )

    def write_rows(self, rows, *, fields=FIELDS):
        with self.csv_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fields,
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
            "import_case001_story_events_v3",
            *args,
            stdout=output,
        )

        return output.getvalue()

    def test_pending_inventory_dry_run_is_safe(self):
        self.write_rows(self.make_rows())

        output = self.run_import()

        self.assertIn("Story candidates: 15", output)
        self.assertIn("Selected events: 0", output)
        self.assertIn("DRY RUN", output)
        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_selected_event_dry_run_rolls_back(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        self.write_rows(rows)

        output = self.run_import()

        self.assertIn("New events: 1", output)
        self.assertIn("DRY RUN", output)
        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_apply_creates_unapproved_event(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        self.write_rows(rows)

        output = self.run_import(apply=True)

        self.assertIn("IMPORT COMMITTED", output)
        self.assertEqual(StoryEvent.objects.count(), 1)

        event = StoryEvent.objects.get(
            event_key="EVT-CH01-001"
        )

        self.assertEqual(
            event.conditions["requiredEvidenceIds"],
            ["E01"],
        )
        self.assertEqual(
            event.metadata["source_story_id"],
            "STORY_001",
        )
        self.assertFalse(event.metadata["runtime_enabled"])
        self.assertFalse(
            event.metadata["backend_contract_approved"]
        )
        self.assertFalse(is_runtime_approved(event))

    def test_repeated_apply_is_idempotent(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        self.write_rows(rows)

        self.run_import(apply=True)
        output = self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 1)
        self.assertIn("Existing events: 1", output)

    def test_unreviewed_selection_is_rejected(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        rows[0]["review_status"] = "PENDING"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_invalid_csv_header_is_rejected(self):
        self.write_rows(
            self.make_rows(),
            fields=("source_story_id",),
        )

        with self.assertRaises(CommandError):
            self.run_import()

    def test_duplicate_story_id_is_rejected(self):
        rows = self.make_rows()
        rows[14]["source_story_id"] = "STORY_001"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import()

    def test_incomplete_inventory_is_rejected(self):
        rows = self.make_rows()
        self.write_rows(rows[:-1])

        with self.assertRaises(CommandError):
            self.run_import()

    def test_evidence_mapping_drift_is_rejected(self):
        rows = self.make_rows()
        rows[0]["related_evidence_ids"] = "E30"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_missing_scene_reference_is_rejected(self):
        rows = self.make_rows()
        self.write_rows(rows)

        Scene.objects.filter(
            pk=self.scenes["STORY_001"].pk
        ).update(metadata={})

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_deep_gate_is_not_auto_imported(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        self.write_rows(rows)

        EvidenceLink.objects.filter(
            pk=self.links["STORY_001"][0].pk
        ).update(relationship="deep_gate")

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_invalid_required_evidence_is_rejected(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        rows[0]["required_evidence_ids"] = "E30"
        self.write_rows(rows)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_conflict_rolls_back_prior_insert(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        self.select_event(rows, 2)
        self.write_rows(rows)

        StoryEvent.objects.create(
            chapter=self.chapter,
            event_key="EVT-CH01-002",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={"requiredEvidenceIds": ["E02"]},
            payload={
                "title": "Existing conflicting content",
                "text": "Existing value must be preserved.",
            },
            metadata={"existing": True},
        )

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertFalse(
            StoryEvent.objects.filter(
                event_key="EVT-CH01-001"
            ).exists()
        )
        self.assertEqual(StoryEvent.objects.count(), 1)

        existing = StoryEvent.objects.get(
            event_key="EVT-CH01-002"
        )
        self.assertEqual(existing.metadata, {"existing": True})

    def test_non_draft_case_is_rejected(self):
        rows = self.make_rows()
        self.select_event(rows, 1)
        self.write_rows(rows)

        self.case.status = Case.Status.PUBLISHED
        self.case.save(update_fields=["status"])

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(StoryEvent.objects.count(), 0)
