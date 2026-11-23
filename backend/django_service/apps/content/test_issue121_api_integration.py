"""Issue #121: cross-endpoint DRF authorization and disclosure tests."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.content.models import (
    Case,
    Chapter,
    Evidence,
    Scene,
    StoryEvent,
)


TOKEN = "issue121-internal-service-token-" + "A" * 40


@override_settings(CONTENT_SERVICE_TOKEN=TOKEN)
class ContentAPIIntegrationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="Synthetic test case",
            status=Case.Status.PUBLISHED,
        )

        cls.chapter = Chapter.objects.create(
            case=cls.case,
            code="CH01",
            order=1,
            title="Test chapter",
        )

        approved_metadata = {
            "runtime_enabled": True,
            "backend_contract_approved": True,
            "internal_secret": "PRIVATE_SCENE_DATA",
        }

        Scene.objects.create(
            case=cls.case,
            chapter=cls.chapter,
            scene_id="SC-0001",
            title="Public scene",
            scene_text="Approved synthetic content",
            visibility=Scene.Visibility.PLAYER_VISIBLE,
            metadata=approved_metadata,
        )

        Scene.objects.create(
            case=cls.case,
            chapter=cls.chapter,
            scene_id="SC-0002",
            title="Engine-only scene",
            scene_text="PRIVATE_ENGINE_CONTENT",
            visibility=Scene.Visibility.ENGINE_ONLY,
            metadata=approved_metadata,
        )

        cls.evidence = Evidence.objects.create(
            case=cls.case,
            evidence_id="E01",
            name="Test evidence",
            metadata={
                "runtime_enabled": True,
                "canon_approved": True,
                "publication_approved": True,
                "internal_secret": "PRIVATE_EVIDENCE_DATA",
            },
        )

        cls.event = StoryEvent.objects.create(
            chapter=cls.chapter,
            event_key="EVT-CH01-001",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={"requiredEvidenceIds": ["E01"]},
            payload={
                "title": "Approved event",
                "text": "Synthetic event content",
            },
            metadata={
                "runtime_enabled": True,
                "backend_contract_approved": True,
                "internal_secret": "PRIVATE_EVENT_DATA",
            },
        )

        cls.urls = {
            "overview": reverse(
                "internal-case-overview",
                kwargs={"case_id": "CASE-001"},
            ),
            "readiness": reverse(
                "internal-content-readiness",
                kwargs={"case_id": "CASE-001"},
            ),
            "scene": reverse(
                "internal-player-scene",
                kwargs={
                    "case_id": "CASE-001",
                    "scene_id": "SC-0001",
                },
            ),
            "evidence": reverse(
                "internal-evidence-requirements",
                kwargs={
                    "case_id": "CASE-001",
                    "evidence_id": "E01",
                },
            ),
            "npc_cards": reverse(
                "internal-approved-npc-cards",
                kwargs={
                    "case_id": "CASE-001",
                    "character_id": "C01",
                },
            ),
            "event": reverse(
                "internal-approved-story-event",
                kwargs={
                    "case_id": "CASE-001",
                    "event_key": "EVT-CH01-001",
                },
            ),
        }

    def authorized_get(self, url):
        return self.client.get(
            url,
            HTTP_X_CONTENT_SERVICE_TOKEN=TOKEN,
        )

    def test_all_internal_routes_reject_missing_token(self):
        for name, url in self.urls.items():
            with self.subTest(endpoint=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_all_internal_routes_reject_invalid_token(self):
        for name, url in self.urls.items():
            with self.subTest(endpoint=name):
                response = self.client.get(
                    url,
                    HTTP_X_CONTENT_SERVICE_TOKEN="invalid",
                )
                self.assertEqual(response.status_code, 403)

    def test_admin_session_does_not_bypass_internal_token(self):
        admin = get_user_model().objects.create_user(
            username="issue121_admin",
            password="TestPassword123!",
            is_staff=True,
        )
        self.client.force_login(admin)

        for name, url in self.urls.items():
            with self.subTest(endpoint=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    @override_settings(CONTENT_SERVICE_TOKEN="")
    def test_unconfigured_token_rejects_all_internal_routes(self):
        for name, url in self.urls.items():
            with self.subTest(endpoint=name):
                response = self.authorized_get(url)
                self.assertEqual(response.status_code, 403)

    def test_oversized_token_is_rejected(self):
        response = self.client.get(
            self.urls["event"],
            HTTP_X_CONTENT_SERVICE_TOKEN="A" * 513,
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_overview_requires_staff_session(self):
        url = reverse(
            "case-overview",
            kwargs={"case_id": "CASE-001"},
        )

        # Service token alone must not grant admin access.
        response = self.authorized_get(url)
        self.assertEqual(response.status_code, 403)

        admin = get_user_model().objects.create_user(
            username="overview_admin",
            password="TestPassword123!",
            is_staff=True,
        )
        self.client.force_login(admin)

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_approved_scene_has_public_fields_only(self):
        response = self.authorized_get(self.urls["scene"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {"scene_id", "chapter", "title", "scene_text"},
        )
        self.assertNotIn(
            "PRIVATE_SCENE_DATA",
            response.content.decode("utf-8"),
        )

    def test_engine_only_scene_is_hidden(self):
        url = reverse(
            "internal-player-scene",
            kwargs={
                "case_id": "CASE-001",
                "scene_id": "SC-0002",
            },
        )

        response = self.authorized_get(url)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(
            "PRIVATE_ENGINE_CONTENT",
            response.content.decode("utf-8"),
        )

    def test_approved_evidence_has_public_fields_only(self):
        response = self.authorized_get(self.urls["evidence"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "evidence_id": "E01",
                "prerequisites": [],
                "player_unlock_verification_required": True,
            },
        )
        self.assertNotIn(
            "PRIVATE_EVIDENCE_DATA",
            response.content.decode("utf-8"),
        )

    def test_unapproved_evidence_is_hidden(self):
        self.evidence.metadata = {"runtime_enabled": False}
        self.evidence.save(update_fields=["metadata"])

        response = self.authorized_get(self.urls["evidence"])
        self.assertEqual(response.status_code, 404)

    def test_duplicate_event_evidence_ids_are_rejected(self):
        self.event.conditions = {
            "requiredEvidenceIds": ["E01", "E01"],
        }
        self.event.save(update_fields=["conditions"])

        response = self.authorized_get(self.urls["event"])
        self.assertEqual(response.status_code, 404)

    def test_empty_event_title_is_rejected(self):
        self.event.payload = {
            "title": "   ",
            "text": "Content",
        }
        self.event.save(update_fields=["payload"])

        response = self.authorized_get(self.urls["event"])
        self.assertEqual(response.status_code, 404)

    def test_wrong_case_cannot_access_event(self):
        url = reverse(
            "internal-approved-story-event",
            kwargs={
                "case_id": "CASE-999",
                "event_key": "EVT-CH01-001",
            },
        )

        response = self.authorized_get(url)
        self.assertEqual(response.status_code, 404)

    def test_unpublished_case_blocks_player_content(self):
        self.case.status = Case.Status.DRAFT
        self.case.save(update_fields=["status"])

        for name in ("scene", "evidence", "event"):
            with self.subTest(endpoint=name):
                response = self.authorized_get(self.urls[name])
                self.assertEqual(response.status_code, 404)

    def test_readiness_reports_runtime_approval_counts(self):
        response = self.authorized_get(self.urls["readiness"])

        self.assertEqual(response.status_code, 200)
        resources = response.data["resources"]

        # Readiness counts runtime approval, not player visibility.
        self.assertEqual(
            resources["scenes"],
            {"total": 2, "approved": 2, "blocked": 0},
        )
        self.assertEqual(
            resources["evidence"],
            {"total": 1, "approved": 1, "blocked": 0},
        )
