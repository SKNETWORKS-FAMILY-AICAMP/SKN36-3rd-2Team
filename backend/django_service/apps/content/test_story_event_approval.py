
"""Issue #120 - StoryEvent 런타임 승인 정책 테스트."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.content.access_policy import is_runtime_approved
from apps.content.models import Case, Chapter, StoryEvent


class StoryEventApprovalTests(TestCase):
    def setUp(self):
        case = Case.objects.create(
            case_id="CASE-001",
            title="테스트 사건",
        )

        self.chapter = Chapter.objects.create(
            case=case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

    def make_event(self, *, metadata=None):
        return StoryEvent(
            chapter=self.chapter,
            event_key="EVT-CH01-001",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={"requiredEvidenceIds": ["E01"]},
            payload={"title": "새로운 단서"},
            metadata=metadata if metadata is not None else {},
        )

    def test_approved_event(self):
        event = self.make_event(
            metadata={
                "runtime_enabled": True,
                "backend_contract_approved": True,
            }
        )
        self.assertTrue(is_runtime_approved(event))

    def test_unapproved_event(self):
        event = self.make_event()
        self.assertFalse(is_runtime_approved(event))

    def test_partial_approval_is_rejected(self):
        event = self.make_event(
            metadata={"runtime_enabled": True}
        )
        self.assertFalse(is_runtime_approved(event))

    def test_empty_conditions_are_rejected(self):
        event = self.make_event(
            metadata={
                "runtime_enabled": True,
                "backend_contract_approved": True,
            }
        )
        event.conditions = {}
        self.assertFalse(is_runtime_approved(event))

    def test_invalid_metadata_is_rejected(self):
        event = self.make_event()
        event.metadata = ["invalid"]

        with self.assertRaises(ValidationError):
            event.full_clean()
