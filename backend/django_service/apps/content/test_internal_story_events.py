
"""Issue #120 - Django 스토리 이벤트 내부 API 보안 테스트."""

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.content.models import Case, Chapter, StoryEvent


TOKEN = "issue120-story-token-" + "A" * 48


@override_settings(CONTENT_SERVICE_TOKEN=TOKEN)
class InternalStoryEventAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="테스트 사건",
            status=Case.Status.PUBLISHED,
        )

        chapter = Chapter.objects.create(
            case=cls.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

        cls.event = StoryEvent.objects.create(
            chapter=chapter,
            event_key="EVT-CH01-001",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={"requiredEvidenceIds": ["E01"]},
            payload={
                "title": "새로운 단서",
                "text": "스토리 이벤트 본문",
            },
            metadata={
                "runtime_enabled": True,
                "backend_contract_approved": True,
                "internal_secret": "PRIVATE_DATA",
            },
        )

        cls.url = reverse(
            "internal-approved-story-event",
            kwargs={
                "case_id": "CASE-001",
                "event_key": "EVT-CH01-001",
            },
        )

    def authenticated_get(self, url=None):
        return self.client.get(
            url or self.url,
            HTTP_X_CONTENT_SERVICE_TOKEN=TOKEN,
        )

    def update_event(self, **fields):
        for key, value in fields.items():
            setattr(self.event, key, value)

        self.event.save(update_fields=list(fields))

    def test_approved_event_returns_200(self):
        response = self.authenticated_get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            "event_key": "EVT-CH01-001",
            "chapter": "CH01",
            "trigger_type": "EVIDENCE_COLLECTED",
            "required_evidence_ids": ["E01"],
            "title": "새로운 단서",
            "text": "스토리 이벤트 본문",
        })
        self.assertNotIn("PRIVATE_DATA", response.content.decode())

    def test_missing_token_returns_403(self):
        self.assertEqual(
            self.client.get(self.url).status_code,
            403,
        )

    def test_invalid_token_returns_403(self):
        response = self.client.get(
            self.url,
            HTTP_X_CONTENT_SERVICE_TOKEN="invalid",
        )
        self.assertEqual(response.status_code, 403)

    def test_draft_case_returns_404(self):
        self.case.status = Case.Status.DRAFT
        self.case.save(update_fields=["status"])

        self.assertEqual(
            self.authenticated_get().status_code,
            404,
        )

    def test_unapproved_event_returns_404(self):
        self.update_event(metadata={"runtime_enabled": False})

        self.assertEqual(
            self.authenticated_get().status_code,
            404,
        )

    def test_invalid_conditions_return_404(self):
        self.update_event(
            conditions={"unknownCondition": ["E01"]}
        )

        self.assertEqual(
            self.authenticated_get().status_code,
            404,
        )

    def test_invalid_payload_returns_404(self):
        self.update_event(
            payload={
                "title": "테스트",
                "internal_secret": "PRIVATE",
            }
        )

        response = self.authenticated_get()

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("PRIVATE", response.content.decode())

    def test_unsupported_trigger_returns_404(self):
        self.update_event(
            trigger_type=StoryEvent.TriggerType.NPC_UNLOCKED
        )

        self.assertEqual(
            self.authenticated_get().status_code,
            404,
        )

    def test_unknown_event_returns_404(self):
        url = reverse(
            "internal-approved-story-event",
            kwargs={
                "case_id": "CASE-001",
                "event_key": "EVT-CH01-999",
            },
        )

        self.assertEqual(
            self.authenticated_get(url).status_code,
            404,
        )

    def test_post_returns_405(self):
        response = self.client.post(
            self.url,
            {"title": "변조 시도"},
            format="json",
            HTTP_X_CONTENT_SERVICE_TOKEN=TOKEN,
        )

        self.assertEqual(response.status_code, 405)
