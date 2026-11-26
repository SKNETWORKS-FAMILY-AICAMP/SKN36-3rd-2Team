"""Issue #192 - independent E30 consent review gate."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import Http404
from django.test import SimpleTestCase

from .models import ContentRelease, Evidence, Scene
from .permissions import HasContentServiceToken
from .release_views import (
    InternalContentReleaseView,
    InternalE30ConsentReviewView,
    e30_review_digest,
)

MODULE = InternalE30ConsentReviewView.__module__


class E30ConsentReviewTests(SimpleTestCase):

    def setUp(self):
        self.base_checksum = "sha256:" + "a" * 64

        self.base = {
            "version": "v0.15.0",
            "checksum": self.base_checksum,
            "manifest": {
                "approved_evidence": {
                    eid: {}
                    for eid in ("E14", "E16", "E18")
                },
            },
        }

        self.evidence = Mock(spec=Evidence)
        self.evidence.evidence_id = "E30"
        self.evidence.name = "Synthetic evidence"
        self.evidence.score = 3
        self.evidence.metadata = {
            "runtime_enabled": True,
            "canon_approved": True,
            "publication_approved": True,
            "content_version": "case001_1120",
            "source_sha256": "b" * 64,
        }

        self.prerequisites = ["E14", "E16", "E18"]

        self.evidence.prerequisites.order_by.return_value.values_list.return_value = (
            self.prerequisites
        )

        self.scene = Mock(spec=Scene)
        self.scene.scene_id = "SC-0405"
        self.scene.chapter = SimpleNamespace(code="CH04")
        self.scene.title = "Synthetic scene"
        self.scene.scene_text = "SYNTHETIC PRIVATE CONTENT"
        self.scene.visibility = "UNLOCKED_ONLY"
        self.scene.metadata = {
            "runtime_enabled": True,
            "backend_contract_approved": True,
            "content_version": "case001_1120",
            "source_sha256": "c" * 64,
        }

        self.review = SimpleNamespace(
            case=Mock(),
            manifest={},
            checksum="",
        )

        self.manifest = {
            "scope": "E30_CONSENT_REVIEW",
            "case_id": "CASE-001",
            "content_version": "case001_1120",
            "base_release_version": "v0.15.0",
            "base_release_checksum": self.base_checksum,
            "evidence_id": "E30",
            "scene_id": "SC-0405",
            "chapter": "CH04",
            "required_evidence": self.prerequisites.copy(),
            "evidence_sha256": e30_review_digest({
                "evidence_id": "E30",
                "name": self.evidence.name,
                "score": 3,
                "prerequisites": self.prerequisites,
                "source_sha256": "b" * 64,
            }),
            "scene_sha256": e30_review_digest({
                "scene_id": "SC-0405",
                "chapter": "CH04",
                "title": self.scene.title,
                "scene_text": self.scene.scene_text,
                "source_sha256": "c" * 64,
            }),
            "consent_ui_approved": True,
        }

        self.set_manifest(self.manifest)

    def set_manifest(self, manifest):
        self.review.manifest = deepcopy(manifest)
        self.review.checksum = (
            "sha256:" + e30_review_digest(manifest)
        )

    def lookup(self, queryset_or_model, **kwargs):
        model = getattr(
            queryset_or_model,
            "model",
            queryset_or_model,
        )

        if model is ContentRelease:
            return self.review

        if model is Evidence:
            return self.evidence

        if model is Scene:
            return self.scene

        raise AssertionError("Unexpected content lookup")

    def invoke(
        self,
        *,
        case_id="CASE-001",
        version="v0.15.0",
        review_version="v0.99.0",
    ):
        with (
            patch.object(
                InternalContentReleaseView,
                "get",
                return_value=SimpleNamespace(data=self.base),
            ),
            patch(
                f"{MODULE}.get_object_or_404",
                side_effect=self.lookup,
            ),
        ):
            return InternalE30ConsentReviewView().get(
                None,
                case_id,
                version,
                review_version,
            )

    def test_valid_review_returns_metadata_only(self):
        response = self.invoke()

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data, {
            "case_id": "CASE-001",
            "release_version": "v0.15.0",
            "release_checksum": self.base_checksum,
            "review_version": "v0.99.0",
            "approved": True,
        })

        self.assertNotIn(
            "SYNTHETIC PRIVATE CONTENT",
            str(response.data),
        )

        self.assertEqual(
            response["Cache-Control"],
            "private, no-store",
        )

    def test_wrong_case_is_denied(self):
        with self.assertRaises(Http404):
            self.invoke(case_id="CASE-002")

    def test_base_release_cannot_be_review_release(self):
        with self.assertRaises(Http404):
            self.invoke(review_version="v0.15.0")

    def test_general_e30_publication_is_denied(self):
        self.base["manifest"]["approved_evidence"]["E30"] = {}

        with self.assertRaises(Http404):
            self.invoke()

    def test_invalid_review_checksum_is_denied(self):
        self.review.checksum = "sha256:" + "0" * 64

        with self.assertRaises(Http404):
            self.invoke()

    def test_review_contract_mismatch_is_denied(self):
        cases = {
            "scope": "INVALID_SCOPE",
            "case_id": "CASE-002",
            "content_version": "case001_v7_1",
            "base_release_version": "v0.1.0",
            "base_release_checksum": "sha256:" + "0" * 64,
            "evidence_id": "E29",
            "scene_id": "SC-0404",
            "chapter": "CH03",
            "required_evidence": ["E14"],
            "evidence_sha256": "0" * 64,
            "scene_sha256": "0" * 64,
            "consent_ui_approved": False,
        }

        for key, value in cases.items():
            with self.subTest(field=key):
                self.set_manifest({
                    **self.manifest,
                    key: value,
                })

                with self.assertRaises(Http404):
                    self.invoke()

    def test_extra_review_fields_are_denied(self):
        self.set_manifest({
            **self.manifest,
            "unexpected": True,
        })

        with self.assertRaises(Http404):
            self.invoke()

    def test_unapproved_evidence_is_denied(self):
        for key in (
            "runtime_enabled",
            "canon_approved",
            "publication_approved",
        ):
            with self.subTest(field=key):
                self.evidence.metadata[key] = False

                try:
                    with self.assertRaises(Http404):
                        self.invoke()
                finally:
                    self.evidence.metadata[key] = True

    def test_unapproved_scene_is_denied(self):
        for key in (
            "runtime_enabled",
            "backend_contract_approved",
        ):
            with self.subTest(field=key):
                self.scene.metadata[key] = False

                try:
                    with self.assertRaises(Http404):
                        self.invoke()
                finally:
                    self.scene.metadata[key] = True

    def test_wrong_scene_visibility_is_denied(self):
        self.scene.visibility = "PLAYER_VISIBLE"

        with self.assertRaises(Http404):
            self.invoke()

    def test_wrong_scene_chapter_is_denied(self):
        self.scene.chapter.code = "CH03"

        with self.assertRaises(Http404):
            self.invoke()

    def test_wrong_evidence_score_is_denied(self):
        self.evidence.score = 99

        with self.assertRaises(Http404):
            self.invoke()

    def test_changed_prerequisites_are_denied(self):
        self.prerequisites.remove("E18")

        with self.assertRaises(Http404):
            self.invoke()

    def test_changed_scene_text_is_denied(self):
        self.scene.scene_text = "Modified after review"

        with self.assertRaises(Http404):
            self.invoke()

    def test_changed_evidence_content_is_denied(self):
        self.evidence.name = "Modified after review"

        with self.assertRaises(Http404):
            self.invoke()

    def test_wrong_content_version_is_denied(self):
        self.evidence.metadata["content_version"] = "case001_v7_1"

        with self.assertRaises(Http404):
            self.invoke()

    def test_unavailable_review_is_denied(self):
        with (
            patch.object(
                InternalContentReleaseView,
                "get",
                return_value=SimpleNamespace(data=self.base),
            ),
            patch(
                f"{MODULE}.get_object_or_404",
                side_effect=Http404,
            ),
        ):
            with self.assertRaises(Http404):
                InternalE30ConsentReviewView().get(
                    None,
                    "CASE-001",
                    "v0.15.0",
                    "v0.99.0",
                )

    def test_base_release_failure_is_denied(self):
        with patch.object(
            InternalContentReleaseView,
            "get",
            side_effect=Http404,
        ):
            with self.assertRaises(Http404):
                InternalE30ConsentReviewView().get(
                    None,
                    "CASE-001",
                    "v0.15.0",
                    "v0.99.0",
                )

    def test_existing_service_token_permission_is_inherited(self):
        self.assertIn(
            HasContentServiceToken,
            InternalE30ConsentReviewView.permission_classes,
        )

        self.assertNotIn(
            "post",
            InternalE30ConsentReviewView.http_method_names,
        )
