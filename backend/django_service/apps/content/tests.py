
"""Django 콘텐츠 핵심 ORM 모델 테스트."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from .services import create_evidence_prerequisite
from .models import (
    Case,
    Chapter,
    Character,
    Evidence,
    EvidencePrerequisite,
    StoryEvent,
    ContentRelease,
    Scene,
    NPCCard,
    NPCDialogueTrigger,
    EvidenceLink,
    CharacterRelationship,
    Objective,
)
from django.db.models.deletion import ProtectedError
from .models import ContentRelease
from django.contrib.auth import get_user_model
from django.urls import reverse

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
import csv

from django.core.management.base import CommandError
class ContentModelTests(TestCase):
    """Case, Chapter, Character 모델의 무결성을 검증합니다."""

    def setUp(self):
        self.case = Case.objects.create(
            case_id="CASE-001",
            title="마지막 기록: 졸업하지 못한 밤",
        )

    def test_case_creation(self):
        """사건이 정상적으로 생성되고 조회되어야 합니다."""
        case = Case.objects.get(case_id="CASE-001")

        self.assertEqual(case.title, "마지막 기록: 졸업하지 못한 밤")
        self.assertEqual(case.status, Case.Status.DRAFT)

    def test_invalid_case_id(self):
        """잘못된 사건 ID는 모델 검증에서 거부되어야 합니다."""
        case = Case(
            case_id="INVALID",
            title="잘못된 사건",
        )

        with self.assertRaises(ValidationError):
            case.full_clean()

    def test_chapter_relation(self):
        """챕터가 사건에 정상적으로 연결되어야 합니다."""
        chapter = Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="첫 번째 기록",
        )

        self.assertEqual(chapter.case, self.case)
        self.assertEqual(
            list(self.case.chapters.all()),
            [chapter],
        )

    def test_duplicate_chapter_code(self):
        """같은 사건에서 챕터 코드는 중복될 수 없습니다."""
        Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

        # 중첩 트랜잭션으로 제약조건 오류를 격리합니다.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Chapter.objects.create(
                    case=self.case,
                    code="CH01",
                    order=2,
                    title="중복 챕터",
                )

    def test_duplicate_chapter_order(self):
        """같은 사건에서 챕터 순서는 중복될 수 없습니다."""
        Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Chapter.objects.create(
                    case=self.case,
                    code="CH02",
                    order=1,
                    title="순서 중복 챕터",
                )

    def test_character_relation(self):
        """NPC가 사건에 정상적으로 연결되어야 합니다."""
        character = Character.objects.create(
            case=self.case,
            character_id="C01",
            name="테스트 NPC",
        )

        self.assertEqual(character.case, self.case)
        self.assertEqual(
            list(self.case.characters.all()),
            [character],
        )

    def test_duplicate_character_id(self):
        """같은 사건에서 NPC ID는 중복될 수 없습니다."""
        Character.objects.create(
            case=self.case,
            character_id="C01",
            name="첫 번째 NPC",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Character.objects.create(
                    case=self.case,
                    character_id="C01",
                    name="중복 NPC",
                )

    def test_case_delete_protected(self):
        """챕터가 연결된 사건은 삭제할 수 없어야 합니다."""
        Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

        with self.assertRaises(ProtectedError):
            self.case.delete()

        self.assertTrue(
            Case.objects.filter(pk=self.case.pk).exists()
        )


class EvidenceStoryEventTests(TestCase):
    """증거, 선행 관계, 스토리 이벤트의 무결성을 검증합니다."""

    def setUp(self):
        self.case = Case.objects.create(
            case_id="CASE-001",
            title="테스트 사건",
        )

        self.other_case = Case.objects.create(
            case_id="CASE-002",
            title="다른 사건",
        )

        self.chapter = Chapter.objects.create(
            case=self.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

        self.character = Character.objects.create(
            case=self.case,
            character_id="C01",
            name="테스트 NPC",
        )

        self.e01 = Evidence.objects.create(
            case=self.case,
            evidence_id="E01",
            name="첫 번째 증거",
            holder=self.character,
            score=1,
        )

        self.e02 = Evidence.objects.create(
            case=self.case,
            evidence_id="E02",
            name="두 번째 증거",
            score=2,
        )

        self.e03 = Evidence.objects.create(
            case=self.case,
            evidence_id="E03",
            name="세 번째 증거",
            score=3,
        )

    def test_nullable_evidence_score(self):
        """미확정 증거 점수를 NULL로 저장할 수 있어야 합니다."""
        evidence = Evidence(
            case=self.case,
            evidence_id="E04",
            name="점수 미확정 증거",
            score=None,
        )

        evidence.full_clean()
        evidence.save()
        evidence.refresh_from_db()

        self.assertIsNone(evidence.score)

    def test_zero_score_distinct_from_null(self):
        """명시적인 0점과 미확정 점수를 구분합니다."""
        evidence = Evidence(
            case=self.case,
            evidence_id="E05",
            name="0점 증거",
            score=0,
        )

        evidence.full_clean()
        evidence.save()
        evidence.refresh_from_db()

        self.assertEqual(evidence.score, 0)
        self.assertIsNotNone(evidence.score)

    def test_evidence_creation(self):
        """증거 생성 및 사건·NPC 관계를 검증합니다."""
        self.assertEqual(self.e01.case, self.case)
        self.assertEqual(self.e01.holder, self.character)
        self.assertEqual(self.e01.score, 1)
        self.assertEqual(self.case.evidence_items.count(), 3)

    def test_invalid_evidence_id(self):
        """E01~E30 범위를 벗어난 ID를 거부합니다."""
        evidence = Evidence(
            case=self.case,
            evidence_id="E31",
            name="잘못된 증거",
        )

        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_duplicate_evidence_id(self):
        """같은 사건에서 중복 증거 ID를 거부합니다."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Evidence.objects.create(
                    case=self.case,
                    evidence_id="E01",
                    name="중복 증거",
                )

    def test_negative_evidence_score(self):
        """음수 점수는 허용하지 않습니다."""
        evidence = Evidence(
            case=self.case,
            evidence_id="E04",
            name="잘못된 점수",
            score=-1,
        )

        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_holder_must_belong_to_same_case(self):
        """다른 사건의 NPC 연결을 거부합니다."""
        other_character = Character.objects.create(
            case=self.other_case,
            character_id="C01",
            name="다른 사건 NPC",
        )

        evidence = Evidence(
            case=self.case,
            evidence_id="E04",
            name="잘못된 NPC 연결",
            holder=other_character,
        )

        with self.assertRaises(ValidationError):
            evidence.full_clean()

    def test_prerequisite_creation(self):
        """정상적인 선행 증거 관계를 생성합니다."""
        relation = EvidencePrerequisite(
            dependent=self.e02,
            prerequisite=self.e01,
        )

        relation.full_clean()
        relation.save()

        self.assertEqual(
            list(self.e02.prerequisites.all()),
            [self.e01],
        )

    def test_duplicate_prerequisite(self):
        """동일 선행 관계 중복을 거부합니다."""
        EvidencePrerequisite.objects.create(
            dependent=self.e02,
            prerequisite=self.e01,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EvidencePrerequisite.objects.create(
                    dependent=self.e02,
                    prerequisite=self.e01,
                )

    def test_self_prerequisite(self):
        """증거가 자기 자신을 요구할 수 없습니다."""
        relation = EvidencePrerequisite(
            dependent=self.e01,
            prerequisite=self.e01,
        )

        with self.assertRaises(ValidationError):
            relation.full_clean()

    def test_cross_case_prerequisite(self):
        """서로 다른 사건의 증거 연결을 거부합니다."""
        other_evidence = Evidence.objects.create(
            case=self.other_case,
            evidence_id="E01",
            name="다른 사건 증거",
        )

        relation = EvidencePrerequisite(
            dependent=self.e02,
            prerequisite=other_evidence,
        )

        with self.assertRaises(ValidationError):
            relation.full_clean()

    def test_circular_prerequisite(self):
        """순환하는 선행 관계를 거부합니다."""
        # E02 requires E01
        EvidencePrerequisite.objects.create(
            dependent=self.e02,
            prerequisite=self.e01,
        )

        # E03 requires E02
        EvidencePrerequisite.objects.create(
            dependent=self.e03,
            prerequisite=self.e02,
        )

        # E01 requires E03 → 순환 발생
        relation = EvidencePrerequisite(
            dependent=self.e01,
            prerequisite=self.e03,
        )

        with self.assertRaises(ValidationError):
            relation.full_clean()

    def test_story_event_creation(self):
        """스토리 이벤트가 정상적으로 생성됩니다."""
        event = StoryEvent(
            chapter=self.chapter,
            event_key="EVT-CH01-001",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={"requiredEvidenceIds": ["E01"]},
            payload={"title": "새로운 단서"},
        )

        event.full_clean()
        event.save()

        self.assertEqual(event.chapter, self.chapter)
        self.assertEqual(
            event.trigger_type,
            StoryEvent.TriggerType.EVIDENCE_COLLECTED,
        )

    def test_invalid_story_event_conditions(self):
        """이벤트 조건은 JSON 객체여야 합니다."""
        event = StoryEvent(
            chapter=self.chapter,
            event_key="EVT-CH01-002",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions=["E01"],
            payload={},
        )

        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_story_event_chapter_mismatch(self):
        """이벤트 키와 소속 챕터는 일치해야 합니다."""
        event = StoryEvent(
            chapter=self.chapter,
            event_key="EVT-CH02-001",
            trigger_type=StoryEvent.TriggerType.EVIDENCE_COLLECTED,
            conditions={},
            payload={},
        )

        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_invalid_story_event_trigger(self):
        """정의되지 않은 이벤트 트리거를 거부합니다."""
        event = StoryEvent(
            chapter=self.chapter,
            event_key="EVT-CH01-003",
            trigger_type="INVALID_TRIGGER",
            conditions={},
            payload={},
        )

        with self.assertRaises(ValidationError):
            event.full_clean()

class EvidencePrerequisiteServiceTests(TestCase):
    """증거 선행 관계 저장 서비스의 검증 및 트랜잭션을 테스트합니다."""

    def setUp(self):
        self.case = Case.objects.create(
            case_id="CASE-001",
            title="서비스 테스트 사건",
        )
        self.other_case = Case.objects.create(
            case_id="CASE-002",
            title="다른 사건",
        )

        self.e01 = Evidence.objects.create(
            case=self.case,
            evidence_id="E01",
            name="첫 번째 증거",
        )
        self.e02 = Evidence.objects.create(
            case=self.case,
            evidence_id="E02",
            name="두 번째 증거",
        )
        self.e03 = Evidence.objects.create(
            case=self.case,
            evidence_id="E03",
            name="세 번째 증거",
        )
        self.other_evidence = Evidence.objects.create(
            case=self.other_case,
            evidence_id="E01",
            name="다른 사건 증거",
        )

    def test_create_valid_relation(self):
        """정상적인 증거 선행 관계가 저장되어야 합니다."""
        relation = create_evidence_prerequisite(
            dependent_id=self.e02.pk,
            prerequisite_id=self.e01.pk,
        )

        self.assertIsNotNone(relation.pk)
        self.assertEqual(relation.dependent, self.e02)
        self.assertEqual(relation.prerequisite, self.e01)

        self.assertTrue(
            self.e02.prerequisites.filter(pk=self.e01.pk).exists()
        )

    def test_create_valid_chain(self):
        """순환하지 않는 다단계 선행 관계를 허용합니다."""
        create_evidence_prerequisite(
            dependent_id=self.e02.pk,
            prerequisite_id=self.e01.pk,
        )
        create_evidence_prerequisite(
            dependent_id=self.e03.pk,
            prerequisite_id=self.e02.pk,
        )

        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            2,
        )

    def test_reject_duplicate_relation(self):
        """동일한 관계를 중복 저장할 수 없습니다."""
        create_evidence_prerequisite(
            dependent_id=self.e02.pk,
            prerequisite_id=self.e01.pk,
        )

        with self.assertRaises(ValidationError):
            create_evidence_prerequisite(
                dependent_id=self.e02.pk,
                prerequisite_id=self.e01.pk,
            )

        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            1,
        )

    def test_reject_self_reference(self):
        """증거가 자기 자신을 선행 조건으로 가질 수 없습니다."""
        with self.assertRaises(ValidationError):
            create_evidence_prerequisite(
                dependent_id=self.e01.pk,
                prerequisite_id=self.e01.pk,
            )

        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            0,
        )

    def test_reject_cross_case_relation(self):
        """다른 사건에 속한 증거는 연결할 수 없습니다."""
        with self.assertRaises(ValidationError):
            create_evidence_prerequisite(
                dependent_id=self.e02.pk,
                prerequisite_id=self.other_evidence.pk,
            )

        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            0,
        )

    def test_reject_circular_relation(self):
        """순환 관계를 거부하고 기존 관계를 유지합니다."""
        # E02 requires E01
        create_evidence_prerequisite(
            dependent_id=self.e02.pk,
            prerequisite_id=self.e01.pk,
        )

        # E03 requires E02
        create_evidence_prerequisite(
            dependent_id=self.e03.pk,
            prerequisite_id=self.e02.pk,
        )

        # E01 requires E03 → 순환 발생
        with self.assertRaises(ValidationError):
            create_evidence_prerequisite(
                dependent_id=self.e01.pk,
                prerequisite_id=self.e03.pk,
            )

        # 실패한 관계는 저장되지 않아야 합니다.
        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            2,
        )

    def test_reject_missing_evidence(self):
        """존재하지 않는 증거 ID를 거부합니다."""
        with self.assertRaises(ValidationError):
            create_evidence_prerequisite(
                dependent_id=self.e01.pk,
                prerequisite_id=999999,
            )

        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            0,
        )

    def test_reject_invalid_id_input(self):
        """정수가 아니거나 0 이하인 ID를 거부합니다."""
        invalid_values = [0, -1, True, "1", None]

        for invalid_id in invalid_values:
            with self.subTest(invalid_id=invalid_id):
                with self.assertRaises(ValidationError):
                    create_evidence_prerequisite(
                        dependent_id=invalid_id,
                        prerequisite_id=self.e01.pk,
                    )

        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            0,
        )


class ContentReleaseTests(TestCase):
    """콘텐츠 게시 버전의 생성, 무결성 및 불변성을 검증합니다."""

    def setUp(self):
        self.case = Case.objects.create(
            case_id="CASE-001",
            title="게시 테스트 사건",
        )
        self.other_case = Case.objects.create(
            case_id="CASE-002",
            title="다른 사건",
        )
        self.manifest = {
            "schema_version": 1,
            "chapters": [],
        }
        # 형식 검증용 테스트 값이며 실제 manifest의 해시가 아닙니다.
        self.checksum = "sha256:" + "a" * 64

    def create_release(self, *, case=None, version="v1.0.0"):
        return ContentRelease.objects.create(
            case=case or self.case,
            version=version,
            manifest=self.manifest.copy(),
            checksum=self.checksum,
        )

    def test_create_release(self):
        """정상적인 게시 버전을 생성합니다."""
        release = self.create_release()

        self.assertIsNotNone(release.pk)
        self.assertIsNotNone(release.published_at)
        self.assertEqual(release.version, "v1.0.0")
        self.assertEqual(self.case.releases.count(), 1)

    def test_reject_duplicate_version(self):
        """동일 사건에 같은 버전을 중복 게시할 수 없습니다."""
        self.create_release()

        with self.assertRaises(ValidationError):
            self.create_release()

        self.assertEqual(ContentRelease.objects.count(), 1)

    def test_allow_same_version_for_different_case(self):
        """서로 다른 사건에서는 같은 버전을 사용할 수 있습니다."""
        self.create_release()
        self.create_release(case=self.other_case)

        self.assertEqual(ContentRelease.objects.count(), 2)

    def test_reject_invalid_version(self):
        """잘못된 버전 형식을 거부합니다."""
        with self.assertRaises(ValidationError):
            self.create_release(version="1.0.0")

    def test_reject_invalid_checksum(self):
        """잘못된 SHA-256 체크섬 형식을 거부합니다."""
        with self.assertRaises(ValidationError):
            ContentRelease.objects.create(
                case=self.case,
                version="v1.0.0",
                manifest=self.manifest,
                checksum="invalid",
            )

    def test_reject_invalid_manifest(self):
        """스냅샷은 JSON 객체여야 합니다."""
        with self.assertRaises(ValidationError):
            ContentRelease.objects.create(
                case=self.case,
                version="v1.0.0",
                manifest=["invalid"],
                checksum=self.checksum,
            )

    def test_reject_instance_update(self):
        """게시된 인스턴스를 수정할 수 없습니다."""
        release = self.create_release()
        release.version = "v2.0.0"

        with self.assertRaises(ValidationError):
            release.save()

        release.refresh_from_db()
        self.assertEqual(release.version, "v1.0.0")

    def test_reject_instance_delete(self):
        """게시된 인스턴스를 삭제할 수 없습니다."""
        release = self.create_release()

        with self.assertRaises(ValidationError):
            release.delete()

        self.assertTrue(
            ContentRelease.objects.filter(pk=release.pk).exists()
        )

    def test_reject_queryset_update(self):
        """QuerySet.update()를 차단합니다."""
        release = self.create_release()

        with self.assertRaises(ValidationError):
            ContentRelease.objects.filter(
                pk=release.pk
            ).update(version="v2.0.0")

        release.refresh_from_db()
        self.assertEqual(release.version, "v1.0.0")

    def test_reject_queryset_delete(self):
        """QuerySet.delete()를 차단합니다."""
        release = self.create_release()

        with self.assertRaises(ValidationError):
            ContentRelease.objects.filter(
                pk=release.pk
            ).delete()

        self.assertEqual(ContentRelease.objects.count(), 1)

    def test_reject_bulk_create(self):
        """save() 검증을 우회하는 대량 생성을 차단합니다."""
        release = ContentRelease(
            case=self.case,
            version="v1.0.0",
            manifest=self.manifest,
            checksum=self.checksum,
        )

        with self.assertRaises(ValidationError):
            ContentRelease.objects.bulk_create([release])

        self.assertEqual(ContentRelease.objects.count(), 0)

    def test_reject_bulk_update(self):
        """대량 수정을 차단합니다."""
        release = self.create_release()
        release.version = "v2.0.0"

        with self.assertRaises(ValidationError):
            ContentRelease.objects.bulk_update(
                [release],
                ["version"],
            )

        release.refresh_from_db()
        self.assertEqual(release.version, "v1.0.0")

    def test_reject_update_or_create(self):
        """기존 게시 버전의 update_or_create 수정을 차단합니다."""
        release = self.create_release()

        with self.assertRaises(ValidationError):
            ContentRelease.objects.update_or_create(
                case=self.case,
                version="v1.0.0",
                defaults={"checksum": "sha256:" + "b" * 64},
            )

        release.refresh_from_db()
        self.assertEqual(release.checksum, self.checksum)

    def test_protect_case_deletion(self):
        """게시 기록이 존재하는 사건의 삭제를 보호합니다."""
        self.create_release()

        with self.assertRaises(ProtectedError):
            self.case.delete()

        self.assertTrue(
            Case.objects.filter(pk=self.case.pk).exists()
        )


class ContentAdminTests(TestCase):
    """Django Admin의 화면 접근, 검색 및 권한을 검증합니다."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.admin_user = user_model.objects.create_superuser(
            username="admin_test",
            email="admin@example.com",
            password="TestPassword123!",
        )

        cls.staff_user = user_model.objects.create_user(
            username="staff_test",
            password="TestPassword123!",
            is_staff=True,
        )

        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="관리자 테스트 사건",
        )

        Case.objects.create(
            case_id="CASE-002",
            title="검색 제외 사건",
        )

        cls.release = ContentRelease.objects.create(
            case=cls.case,
            version="v1.0.0",
            manifest={"chapters": []},
            checksum="sha256:" + "a" * 64,
        )

    def test_extended_admin_add_forms_accessible(self):
        """신규 모델 6개의 Admin 생성 화면이 정상적으로 열리는지 확인합니다."""

        models = (
            "scene",
            "npccard",
            "npcdialoguetrigger",
            "evidencelink",
            "characterrelationship",
            "objective",
        )

        for model_name in models:
            with self.subTest(model=model_name):
                url = reverse(f"admin:content_{model_name}_add")
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="_save"')

    def test_extended_admin_changelists_accessible(self):
        """신규 콘텐츠 모델 6개의 관리자 목록 접근을 검증합니다."""

        models = (
            "scene",
            "npccard",
            "npcdialoguetrigger",
            "evidencelink",
            "characterrelationship",
            "objective",
        )

        for model_name in models:
            with self.subTest(model=model_name):
                url = reverse(
                    f"admin:content_{model_name}_changelist"
                )

                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_all_admin_changelists_accessible(self):
        """슈퍼유저가 7개 관리자 목록에 접근할 수 있습니다."""
        models = (
            "case",
            "chapter",
            "character",
            "evidence",
            "evidenceprerequisite",
            "storyevent",
            "contentrelease",
        )

        for model in models:
            with self.subTest(model=model):
                url = reverse(
                    f"admin:content_{model}_changelist"
                )
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_case_search(self):
        """사건 ID 검색이 올바르게 작동합니다."""
        url = reverse("admin:content_case_changelist")

        response = self.client.get(
            url,
            {"q": "CASE-001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["cl"].result_list),
            [self.case],
        )

    def test_anonymous_access_redirected(self):
        """미인증 사용자는 관리자 로그인으로 이동합니다."""
        self.client.logout()

        url = reverse("admin:content_case_changelist")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_without_permission_denied(self):
        """모델 권한이 없는 직원의 접근을 차단합니다."""
        self.client.force_login(self.staff_user)

        urls = (
            reverse("admin:content_case_changelist"),
            reverse(
                "admin:content_contentrelease_changelist"
            ),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_release_detail_readonly_visible(self):
        """슈퍼유저는 게시 버전 상세 정보를 조회할 수 있습니다."""
        url = reverse(
            "admin:content_contentrelease_change",
            args=[self.release.pk],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "v1.0.0")

    def test_release_add_blocked(self):
        """Admin을 통한 게시 버전 생성을 차단합니다."""
        url = reverse(
            "admin:content_contentrelease_add"
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)

    def test_release_update_blocked(self):
        """Admin을 통한 게시 버전 수정을 차단합니다."""
        url = reverse(
            "admin:content_contentrelease_change",
            args=[self.release.pk],
        )

        response = self.client.post(
            url,
            {"version": "v2.0.0"},
        )

        self.assertEqual(response.status_code, 403)

        self.release.refresh_from_db()
        self.assertEqual(self.release.version, "v1.0.0")

    def test_release_delete_blocked(self):
        """Admin을 통한 게시 버전 삭제를 차단합니다."""
        url = reverse(
            "admin:content_contentrelease_delete",
            args=[self.release.pk],
        )

        response = self.client.post(
            url,
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            ContentRelease.objects.filter(
                pk=self.release.pk
            ).exists()
        )


class ContentAdminFormIntegrationTests(TestCase):
    """관리자 입력 폼에서 콘텐츠 무결성이 유지되는지 검증합니다."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin_user = user_model.objects.create_superuser(
            username="integration_admin",
            email="integration@example.com",
            password="TestPassword123!",
        )

        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="통합 테스트 사건",
        )
        cls.other_case = Case.objects.create(
            case_id="CASE-002",
            title="다른 테스트 사건",
        )

        cls.chapter = Chapter.objects.create(
            case=cls.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )

        cls.other_character = Character.objects.create(
            case=cls.other_case,
            character_id="C01",
            name="다른 사건 NPC",
        )

        cls.e01 = Evidence.objects.create(
            case=cls.case,
            evidence_id="E01",
            name="첫 번째 증거",
        )
        cls.e02 = Evidence.objects.create(
            case=cls.case,
            evidence_id="E02",
            name="두 번째 증거",
        )
        cls.e03 = Evidence.objects.create(
            case=cls.case,
            evidence_id="E03",
            name="세 번째 증거",
        )
        cls.other_evidence = Evidence.objects.create(
            case=cls.other_case,
            evidence_id="E01",
            name="다른 사건 증거",
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def post_add(self, model_name, data):
        url = reverse(f"admin:content_{model_name}_add")
        return self.client.post(url, data=data)

    def test_chapter_admin_create(self):
        """관리자 폼으로 정상적인 챕터를 생성합니다."""
        response = self.post_add("chapter", {
            "case": self.case.pk,
            "code": "CH02",
            "order": 2,
            "title": "두 번째 챕터",
            "summary": "",
            "metadata": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Chapter.objects.filter(
                case=self.case,
                code="CH02",
            ).exists()
        )

    def test_character_admin_create(self):
        """관리자 폼으로 정상적인 NPC를 생성합니다."""
        response = self.post_add("character", {
            "case": self.case.pk,
            "character_id": "C02",
            "name": "테스트 NPC",
            "profile": "공개 프로필",
            "metadata": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Character.objects.filter(
                case=self.case,
                character_id="C02",
            ).exists()
        )

    def test_evidence_cross_case_holder_rejected(self):
        """다른 사건의 NPC를 증거에 연결할 수 없습니다."""
        response = self.post_add("evidence", {
            "case": self.case.pk,
            "evidence_id": "E04",
            "name": "잘못된 증거",
            "holder": self.other_character.pk,
            "score": 10,
            "metadata": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors
        self.assertIn("holder", errors)
        self.assertFalse(
            Evidence.objects.filter(
                case=self.case,
                evidence_id="E04",
            ).exists()
        )

    def test_prerequisite_cross_case_rejected(self):
        """Admin에서 사건 간 증거 관계를 생성할 수 없습니다."""
        response = self.post_add("evidenceprerequisite", {
            "dependent": self.e02.pk,
            "prerequisite": self.other_evidence.pk,
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors
        self.assertIn("prerequisite", errors)
        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            0,
        )

    def test_prerequisite_cycle_rejected(self):
        """Admin에서도 순환하는 증거 관계를 차단합니다."""
        EvidencePrerequisite.objects.create(
            dependent=self.e02,
            prerequisite=self.e01,
        )
        EvidencePrerequisite.objects.create(
            dependent=self.e03,
            prerequisite=self.e02,
        )

        response = self.post_add("evidenceprerequisite", {
            "dependent": self.e01.pk,
            "prerequisite": self.e03.pk,
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors
        self.assertIn("prerequisite", errors)
        self.assertEqual(
            EvidencePrerequisite.objects.count(),
            2,
        )

    def test_story_event_chapter_mismatch_rejected(self):
        """이벤트 키가 소속 챕터와 다르면 저장하지 않습니다."""
        response = self.post_add("storyevent", {
            "chapter": self.chapter.pk,
            "event_key": "EVT-CH02-001",
            "trigger_type": "CHAPTER_STARTED",
            "conditions": "{}",
            "payload": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors
        self.assertIn("event_key", errors)
        self.assertFalse(
            StoryEvent.objects.filter(
                event_key="EVT-CH02-001"
            ).exists()
        )

    def test_story_event_invalid_conditions_rejected(self):
        """조건 JSON이 배열이면 저장을 차단합니다."""
        response = self.post_add("storyevent", {
            "chapter": self.chapter.pk,
            "event_key": "EVT-CH01-001",
            "trigger_type": "EVIDENCE_COLLECTED",
            "conditions": "[]",
            "payload": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors
        self.assertIn("conditions", errors)
        self.assertFalse(
            StoryEvent.objects.filter(
                event_key="EVT-CH01-001"
            ).exists()
        )

    def test_scene_admin_create(self):
        """Admin에서 정상적인 스토리 장면을 생성합니다."""
        response = self.post_add("scene", {
            "case": self.case.pk,
            "chapter": self.chapter.pk,
            "scene_id": "SC-0001",
            "title": "프롤로그",
            "scene_text": "사건이 시작됩니다.",
            "visibility": "UNLOCKED_ONLY",
            "metadata": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Scene.objects.filter(
                case=self.case,
                scene_id="SC-0001",
            ).exists()
        )

    def test_scene_admin_cross_case_rejected(self):
        """다른 사건의 챕터를 연결하면 저장을 거부합니다."""
        response = self.post_add("scene", {
            "case": self.other_case.pk,
            "chapter": self.chapter.pk,
            "scene_id": "SC-0002",
            "title": "잘못된 장면",
            "scene_text": "사건이 일치하지 않습니다.",
            "visibility": "UNLOCKED_ONLY",
            "metadata": "{}",
            "_save": "Save",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "chapter",
            response.context["adminform"].form.errors,
        )
        self.assertFalse(
            Scene.objects.filter(
                scene_id="SC-0002",
            ).exists()
        )


class ExtendedContentModelTests(TestCase):
    """확장 콘텐츠 모델 6종의 저장 및 무결성 검증."""

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="확장 콘텐츠 테스트",
        )
        cls.other_case = Case.objects.create(
            case_id="CASE-002",
            title="다른 사건",
        )

        cls.chapter = Chapter.objects.create(
            case=cls.case,
            code="CH01",
            order=1,
            title="첫 번째 챕터",
        )
        cls.other_chapter = Chapter.objects.create(
            case=cls.other_case,
            code="CH01",
            order=1,
            title="다른 챕터",
        )

        cls.character = Character.objects.create(
            case=cls.case,
            character_id="C01",
            name="테스트 NPC",
        )

        cls.e01 = Evidence.objects.create(
            case=cls.case,
            evidence_id="E01",
            name="첫 번째 증거",
        )
        cls.e02 = Evidence.objects.create(
            case=cls.case,
            evidence_id="E02",
            name="두 번째 증거",
        )
        cls.other_evidence = Evidence.objects.create(
            case=cls.other_case,
            evidence_id="E01",
            name="다른 사건 증거",
        )

    # 1. Scene
    def test_scene_creation(self):
        scene = Scene.objects.create(
            case=self.case,
            chapter=self.chapter,
            scene_id="SC-0001",
            title="사건의 시작",
            scene_text="첫 번째 장면입니다.",
        )

        self.assertEqual(
            scene.visibility,
            Scene.Visibility.UNLOCKED_ONLY,
        )

    def test_scene_cross_case_rejected(self):
        with self.assertRaises(ValidationError):
            Scene.objects.create(
                case=self.case,
                chapter=self.other_chapter,
                scene_id="SC-0001",
                title="잘못된 장면",
                scene_text="다른 사건의 챕터",
            )

    # 2. NPCCard
    def test_npc_card_creation(self):
        card = NPCCard.objects.create(
            character=self.character,
            card_id="K-C01-01",
            card_type=NPCCard.CardType.KNOWLEDGE,
            content="NPC가 알고 있는 사실",
        )

        self.assertEqual(card.character, self.character)

    def test_npc_card_id_mismatch_rejected(self):
        with self.assertRaises(ValidationError):
            NPCCard.objects.create(
                character=self.character,
                card_id="K-C02-01",
                card_type=NPCCard.CardType.KNOWLEDGE,
                content="다른 NPC의 카드",
            )

    # 3. NPCDialogueTrigger
    def test_dialogue_trigger_creation(self):
        trigger = NPCDialogueTrigger.objects.create(
            character=self.character,
            trigger_id="DT-C01-001",
            stage=1,
            trigger_type="question",
            output_mode="fixed",
            response_text="무엇을 알고 싶으신가요?",
            condition_key="always",
        )

        self.assertFalse(trigger.is_active)

    def test_invalid_dialogue_stage_rejected(self):
        with self.assertRaises(ValidationError):
            NPCDialogueTrigger.objects.create(
                character=self.character,
                trigger_id="DT-C01-002",
                stage=4,
                trigger_type="question",
                output_mode="reference",
                response_text="잘못된 단계",
                condition_key="always",
            )

    # 4. EvidenceLink
    def test_evidence_link_creation(self):
        link = EvidenceLink.objects.create(
            from_evidence=self.e01,
            to_evidence=self.e02,
            relationship="supports",
        )

        self.assertTrue(link.needs_canon_approval)
        self.assertFalse(link.is_active)

    def test_unapproved_evidence_link_rejected(self):
        with self.assertRaises(ValidationError):
            EvidenceLink.objects.create(
                from_evidence=self.e01,
                to_evidence=self.e02,
                relationship="supports",
                needs_canon_approval=True,
                is_active=True,
            )

    def test_evidence_link_cross_case_rejected(self):
        with self.assertRaises(ValidationError):
            EvidenceLink.objects.create(
                from_evidence=self.e01,
                to_evidence=self.other_evidence,
                relationship="supports",
            )

    # 5. CharacterRelationship
    def test_character_relationship_creation(self):
        relation = CharacterRelationship.objects.create(
            source_character=self.character,
            target_type="evidence",
            target_id="E01",
            relationship="NPC가 증거를 보유함",
            public_from_stage=1,
        )

        self.assertFalse(relation.is_active)

    def test_missing_relationship_target_rejected(self):
        with self.assertRaises(ValidationError):
            CharacterRelationship.objects.create(
                source_character=self.character,
                target_type="evidence",
                target_id="E30",
                relationship="존재하지 않는 증거",
                public_from_stage=1,
            )

    # 6. Objective
    def test_objective_creation(self):
        objective = Objective.objects.create(
            chapter=self.chapter,
            objective_id="OBJ_001",
            player_goal="사건 현장을 조사하세요.",
            hints=["현장으로 이동하세요."],
        )

        self.assertFalse(objective.is_active)
        self.assertEqual(objective.completion_rule, {})

    def test_objective_without_rule_rejected(self):
        with self.assertRaises(ValidationError):
            Objective.objects.create(
                chapter=self.chapter,
                objective_id="OBJ_002",
                player_goal="증거를 찾으세요.",
                hints=["책상을 확인하세요."],
                completion_rule={},
                is_active=True,
            )


class FoundationImportCommandTests(TestCase):
    """CASE-001 기초 데이터 Import의 롤백과 멱등성을 검증합니다."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source_root = Path(self.temp_dir.name)
        data_dir = self.source_root / "legacy_source" / "data"
        data_dir.mkdir(parents=True)

        npc_ids = [f"C{i:02d}" for i in range(1, 11)]
        evidence_ids = [f"E{i:02d}" for i in range(1, 11)]

        sources = {
            "character_registry.json": {
                npc_id: {} for npc_id in npc_ids
            },
            "characters.json": [
                {
                    "id": npc_id,
                    "name": f"NPC {npc_id}",
                    "secret_2026": "INTERNAL_SECRET",
                }
                for npc_id in npc_ids
            ],
            "evidence_rules.json": {
                evidence_id: {
                    "name": f"Evidence {evidence_id}",
                    "score": 1,
                    "holder": "C01",
                    "prerequisites": (
                        ["E01"] if evidence_id == "E02" else []
                    ),
                }
                for evidence_id in evidence_ids
            },
        }

        for filename, data in sources.items():
            (data_dir / filename).write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_foundation",
            legacy_root=self.source_root,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run에서는 데이터가 저장되지 않아야 합니다."""
        output = self.run_import()

        self.assertIn("DRY RUN", output)
        self.assertFalse(
            Case.objects.filter(case_id="CASE-001").exists()
        )
        self.assertEqual(Chapter.objects.count(), 0)
        self.assertEqual(Character.objects.count(), 0)
        self.assertEqual(Evidence.objects.count(), 0)
        self.assertEqual(EvidencePrerequisite.objects.count(), 0)

    def test_apply_is_idempotent(self):
        """두 번 실행해도 동일한 데이터가 중복 생성되지 않습니다."""
        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("IMPORT COMMITTED", first)
        self.assertIn("IMPORT COMMITTED", second)
        self.assertIn("case: +0", second)
        self.assertIn("chapter: +0", second)
        self.assertIn("character: +0", second)
        self.assertIn("evidence: +0", second)
        self.assertIn("prerequisite: +0", second)

        self.assertEqual(Case.objects.count(), 1)
        self.assertEqual(Chapter.objects.count(), 5)
        self.assertEqual(Character.objects.count(), 10)
        self.assertEqual(Evidence.objects.count(), 10)
        self.assertEqual(EvidencePrerequisite.objects.count(), 1)

        # 비공개 NPC 정보가 공개 프로필에 포함되지 않았는지 확인합니다.
        npc = Character.objects.get(character_id="C01")
        self.assertNotIn("INTERNAL_SECRET", npc.profile)
        self.assertNotIn("INTERNAL_SECRET", str(npc.metadata))


class ExtendedEvidenceImportCommandTests(TestCase):
    """E11~E30 Import의 롤백, 멱등성 및 참조 무결성을 검증합니다."""

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="마지막 기록: 졸업하지 못한 밤",
        )

        for number in range(5):
            Chapter.objects.create(
                case=cls.case,
                code=f"CH{number:02d}",
                order=number,
                title=f"CH{number:02d}",
            )

        cls.character = Character.objects.create(
            case=cls.case,
            character_id="C01",
            name="테스트 NPC",
        )

        cls.baseline = Evidence.objects.create(
            case=cls.case,
            evidence_id="E01",
            name="기존 증거",
            holder=cls.character,
            score=5,
        )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.csv_path = Path(self.temp_dir.name) / "evidence.csv"

    def write_source(self, *, invalid_holder=False):
        """테스트용 증거 20건을 생성합니다."""
        columns = [
            "evidence_id",
            "title",
            "holder_npc_id",
            "chapter",
            "score_points",
            "access_scope",
            "canon_status",
        ]

        with self.csv_path.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()

            for number in range(11, 31):
                writer.writerow({
                    "evidence_id": f"E{number:02d}",
                    "title": f"테스트 증거 E{number:02d}",
                    "holder_npc_id": (
                        "C99"
                        if invalid_holder and number == 30
                        else "C01"
                    ),
                    "chapter": "CH01",
                    "score_points": "미정(백엔드)",
                    "access_scope": "UNLOCKED_ONLY",
                    "canon_status": "초안",
                })

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_extended_evidence",
            source=self.csv_path,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run은 신규 증거를 DB에 저장하지 않습니다."""
        self.write_source()

        output = self.run_import()

        self.assertIn("DRY RUN", output)
        self.assertEqual(
            Evidence.objects.filter(case=self.case).count(),
            1,
        )

    def test_apply_is_idempotent(self):
        """동일 파일을 두 번 Import해도 중복 생성되지 않습니다."""
        self.write_source()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New evidence: 20", first)
        self.assertIn("New evidence: 0", second)
        self.assertIn("Existing evidence: 20", second)

        self.assertEqual(
            Evidence.objects.filter(case=self.case).count(),
            21,
        )

        new_items = Evidence.objects.filter(
            case=self.case,
            evidence_id__in=[
                f"E{i:02d}" for i in range(11, 31)
            ],
        )

        self.assertEqual(new_items.filter(score__isnull=True).count(), 20)

        self.assertTrue(all(
            item.metadata.get("runtime_enabled") is False
            for item in new_items
        ))

        self.assertTrue(all(
            item.metadata.get("score_status") == "UNDEFINED"
            for item in new_items
        ))

    def test_invalid_holder_rolls_back_all(self):
        """마지막 증거의 NPC 참조가 잘못되면 전체 롤백합니다."""
        self.write_source(invalid_holder=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(
            Evidence.objects.filter(case=self.case).count(),
            1,
        )

        self.assertFalse(
            Evidence.objects.filter(
                case=self.case,
                evidence_id="E11",
            ).exists()
        )

    def test_baseline_evidence_unchanged(self):
        """E11~E30 Import가 기존 E01 정보를 변경하지 않습니다."""
        self.write_source()
        self.run_import(apply=True)

        self.baseline.refresh_from_db()

        self.assertEqual(self.baseline.name, "기존 증거")
        self.assertEqual(self.baseline.score, 5)
        self.assertEqual(
            self.baseline.holder_id,
            self.character.pk,
        )


class SceneImportCommandTests(TestCase):
    """Scene Import의 롤백, 멱등성 및 공개 정책을 검증합니다."""

    CHAPTER_COUNTS = {
        "CH00": 5,
        "CH01": 5,
        "CH02": 6,
        "CH03": 9,
        "CH04": 5,
    }

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="Scene Import 테스트 사건",
        )

        for number in range(5):
            Chapter.objects.create(
                case=cls.case,
                code=f"CH{number:02d}",
                order=number,
                title=f"챕터 {number}",
            )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source_path = (
            Path(self.temp_dir.name) / "scenes.json"
        )

    def write_source(self, *, invalid_visibility=False):
        """원본 스키마와 동일한 장면 30건을 생성합니다."""
        scenes = []

        for chapter, count in self.CHAPTER_COUNTS.items():
            chapter_number = int(chapter[2:])

            for number in range(1, count + 1):
                scene_id = (
                    f"SC-{chapter_number:02d}{number:02d}"
                )

                visibility = (
                    "ENGINE_ONLY_UNTIL_UNLOCK"
                    if chapter == "CH03" and number <= 2
                    else "UNLOCKED_ONLY"
                )

                scenes.append({
                    "scene_id": scene_id,
                    "chapter": chapter,
                    "title": f"테스트 장면 {scene_id}",
                    "scene_text": f"{scene_id}의 테스트 원고",
                    "visibility": visibility,
                    "status": "CONTENT_FINAL_ENGINE_PENDING",
                    "event_id_proposal": None,
                    "puzzle": {},
                })

        if invalid_visibility:
            scenes[0]["visibility"] = "PLAYER_VISIBLE"

        payload = {
            "schema_version": "case001-scenes-2026-11-20",
            "not_backend_contract": True,
            "scenes": scenes,
        }

        self.source_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_scenes",
            source=self.source_path,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run은 Scene을 저장하지 않아야 합니다."""
        self.write_source()

        output = self.run_import()

        self.assertIn("New scenes: 30", output)
        self.assertIn("DRY RUN", output)
        self.assertEqual(Scene.objects.count(), 0)

    def test_apply_is_idempotent_and_safe(self):
        """중복 생성 없이 공개 제한을 유지합니다."""
        self.write_source()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New scenes: 30", first)
        self.assertIn("New scenes: 0", second)
        self.assertIn("Existing scenes: 30", second)

        scenes = Scene.objects.filter(case=self.case)

        self.assertEqual(scenes.count(), 30)

        self.assertEqual(
            scenes.filter(
                visibility=Scene.Visibility.UNLOCKED_ONLY
            ).count(),
            28,
        )

        self.assertEqual(
            scenes.filter(
                visibility=Scene.Visibility.ENGINE_ONLY
            ).count(),
            2,
        )

        for scene in scenes:
            self.assertIs(
                scene.metadata["runtime_enabled"],
                False,
            )
            self.assertIs(
                scene.metadata["backend_contract_approved"],
                False,
            )

            if scene.visibility == Scene.Visibility.ENGINE_ONLY:
                self.assertEqual(
                    scene.metadata["source_visibility"],
                    "ENGINE_ONLY_UNTIL_UNLOCK",
                )

    def test_existing_conflict_rolls_back_all(self):
        """마지막 장면에서 충돌하면 앞선 생성도 롤백합니다."""
        self.write_source()

        chapter = Chapter.objects.get(
            case=self.case,
            code="CH04",
        )

        Scene.objects.create(
            case=self.case,
            chapter=chapter,
            scene_id="SC-0405",
            title="기존에 저장된 다른 장면",
            scene_text="변경하면 안 되는 원고",
        )

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        # 앞선 29건도 롤백되고 기존 1건만 남아야 합니다.
        self.assertEqual(Scene.objects.count(), 1)

        existing = Scene.objects.get(scene_id="SC-0405")
        self.assertEqual(
            existing.title,
            "기존에 저장된 다른 장면",
        )

        self.assertFalse(
            Scene.objects.filter(
                scene_id="SC-0001"
            ).exists()
        )

    def test_unknown_visibility_rejected(self):
        """허용되지 않은 공개 범위를 거부합니다."""
        self.write_source(invalid_visibility=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(Scene.objects.count(), 0)


class NPCCardImportCommandTests(TestCase):
    """NPC 카드 Import의 멱등성, 롤백, 참조 검증."""

    KNOWLEDGE_COUNTS = {
        "C01": 17, "C02": 13, "C03": 9,
        "C04": 9, "C05": 7, "C06": 7,
        "C07": 8, "C08": 9, "C09": 11,
        "C10": 10,
    }

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="NPC 카드 Import 테스트",
        )

        for number in range(1, 11):
            Character.objects.create(
                case=cls.case,
                character_id=f"C{number:02d}",
                name=f"NPC {number}",
            )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.source_dir = Path(self.temp_dir.name)

    def write_sources(self, *, invalid_npc=False):
        knowledge_columns = [
            "npc_id", "card_id", "내용", "지식상태",
            "인식시점", "본적있는증거", "조건전_태도",
            "공개조건", "조건후_태도",
            "잠겼을때_답변방향", "근거",
        ]

        smalltalk_columns = [
            "npc_id", "card_id", "대화주제",
            "알고있는사실", "답변범위", "답변제한",
            "말투", "참고예시", "공개조건", "근거",
        ]

        knowledge_path = (
            self.source_dir / "08_NPC_KNOWLEDGE_CARDS.csv"
        )
        smalltalk_path = (
            self.source_dir / "08_NPC_SMALLTALK_CARDS.csv"
        )

        with knowledge_path.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(
                file, fieldnames=knowledge_columns
            )
            writer.writeheader()

            for npc_id, count in self.KNOWLEDGE_COUNTS.items():
                for number in range(1, count + 1):
                    writer.writerow({
                        "npc_id": npc_id,
                        "card_id": f"K-{npc_id}-{number:02d}",
                        "내용": f"{npc_id} 테스트 지식 {number}",
                        "지식상태": "알고 있음",
                        "인식시점": "현재",
                        "본적있는증거": "",
                        "조건전_태도": "공개 제한",
                        "공개조건": "검증 전 비공개",
                        "조건후_태도": "변경 가능",
                        "잠겼을때_답변방향": "답변 보류",
                        "근거": "테스트 Fixture",
                    })

        with smalltalk_path.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(
                file, fieldnames=smalltalk_columns
            )
            writer.writeheader()

            for number in range(1, 11):
                npc_id = f"C{number:02d}"

                for index in range(1, 5):
                    # 마지막 행에서 잘못된 NPC 참조를 주입합니다.
                    source_npc = (
                        "C99"
                        if invalid_npc
                        and npc_id == "C10"
                        and index == 4
                        else npc_id
                    )

                    writer.writerow({
                        "npc_id": source_npc,
                        "card_id": f"K-{source_npc}-S{index:02d}",
                        "대화주제": f"주제 {index}",
                        "알고있는사실": "일상 대화용 사실",
                        "답변범위": "일반 대화",
                        "답변제한": "비밀 공개 금지",
                        "말투": "차분함",
                        "참고예시": "일반적인 답변",
                        "공개조건": "검증 전 비공개",
                        "근거": "테스트 Fixture",
                    })

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_npc_cards",
            source_dir=self.source_dir,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run은 카드 데이터를 저장하지 않습니다."""
        self.write_sources()

        result = self.run_import()

        self.assertIn("DRY RUN", result)
        self.assertEqual(NPCCard.objects.count(), 0)

    def test_apply_is_idempotent(self):
        """반복 Import 시 카드 140건을 유지합니다."""
        self.write_sources()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New cards: 140", first)
        self.assertIn("New cards: 0", second)
        self.assertIn("Existing cards: 140", second)

        self.assertEqual(NPCCard.objects.count(), 140)
        self.assertEqual(
            NPCCard.objects.filter(card_type="KNOWLEDGE").count(),
            100,
        )
        self.assertEqual(
            NPCCard.objects.filter(card_type="SMALLTALK").count(),
            40,
        )

    def test_invalid_npc_rolls_back(self):
        """잘못된 NPC 참조로 인해 전체 Import가 롤백됩니다."""
        self.write_sources(invalid_npc=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(NPCCard.objects.count(), 0)

    def test_disclosure_not_automatically_enabled(self):
        """공개 조건이 평가되기 전 카드를 자동 활성화하지 않습니다."""
        self.write_sources()
        self.run_import(apply=True)

        for card in NPCCard.objects.all():
            self.assertIsInstance(card.disclosure_policy, dict)
            self.assertIsNot(
                card.disclosure_policy.get("runtime_enabled"),
                True,
            )


class NPCDialogueTriggerImportTests(TestCase):
    """NPC 대화 트리거 Import의 안전성과 멱등성을 검증합니다."""

    NPC_COUNTS = {
        "C01": 25, "C02": 17, "C03": 14,
        "C04": 13, "C05": 15, "C06": 14,
        "C07": 13, "C08": 19, "C09": 14,
        "C10": 22,
    }

    COLUMNS = [
        "npc_id",
        "stage",
        "trigger_type",
        "evidence_ids",
        "response_text",
        "tag",
        "next_stage",
        "repeat_variant",
        "draft_status",
        "source_basis",
        "condition_key",
        "output_order",
        "output_mode",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="대화 트리거 Import 테스트",
            status=Case.Status.DRAFT,
        )

        for number in range(1, 11):
            Character.objects.create(
                case=cls.case,
                character_id=f"C{number:02d}",
                name=f"NPC {number}",
            )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source = (
            Path(self.temp_dir.name) / "dialogue_triggers.csv"
        )

    def write_source(self, *, invalid_type=False):
        """원본과 같은 건수 및 분포의 임시 CSV를 생성합니다."""

        global_index = 0

        with self.source.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.COLUMNS,
            )
            writer.writeheader()

            for npc_id, count in self.NPC_COUNTS.items():
                for order in range(1, count + 1):
                    global_index += 1

                    if global_index <= 60:
                        trigger_type = "question"
                    elif global_index <= 100:
                        trigger_type = "verbal_only"
                    elif global_index <= 148:
                        trigger_type = "evidence"
                    else:
                        trigger_type = "evidence_combo"

                    if global_index <= 100:
                        stage = 1
                    elif global_index <= 149:
                        stage = 2
                    else:
                        stage = 3

                    if global_index <= 101:
                        next_stage = "유지"
                    elif global_index <= 149:
                        next_stage = "2"
                    else:
                        next_stage = "3"

                    if invalid_type and global_index == 166:
                        trigger_type = "invalid_type"

                    writer.writerow({
                        "npc_id": npc_id,
                        "stage": stage,
                        "trigger_type": trigger_type,
                        "evidence_ids": "",
                        "response_text": (
                            f"{npc_id} 테스트 대사 {order}"
                        ),
                        "tag": "test",
                        "next_stage": next_stage,
                        "repeat_variant": "",
                        "draft_status": "초안",
                        "source_basis": "test_fixture",
                        "condition_key": "test_condition",
                        "output_order": order,
                        "output_mode": (
                            "reference"
                            if global_index <= 90
                            else "fixed"
                        ),
                    })

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_dialogue_triggers",
            source=self.source,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run에서는 데이터를 저장하지 않습니다."""
        self.write_source()

        result = self.run_import()

        self.assertIn("New triggers: 166", result)
        self.assertIn("DRY RUN", result)
        self.assertEqual(
            NPCDialogueTrigger.objects.count(),
            0,
        )

    def test_apply_is_idempotent_and_inactive(self):
        """재실행 시 중복 생성 없이 비활성 상태를 유지합니다."""
        self.write_source()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New triggers: 166", first)
        self.assertIn("New triggers: 0", second)
        self.assertIn("Existing triggers: 166", second)

        triggers = list(
            NPCDialogueTrigger.objects.all()
        )

        self.assertEqual(len(triggers), 166)
        self.assertEqual(
            len({t.trigger_id for t in triggers}),
            166,
        )

        for trigger in triggers:
            self.assertFalse(trigger.is_active)
            self.assertIs(
                trigger.metadata["runtime_enabled"],
                False,
            )
            self.assertIs(
                trigger.metadata["condition_approved"],
                False,
            )

    def test_existing_conflict_rolls_back_all(self):
        """마지막 트리거 충돌 시 앞선 생성도 롤백합니다."""
        character = Character.objects.get(
            case=self.case,
            character_id="C10",
        )

        NPCDialogueTrigger.objects.create(
            character=character,
            trigger_id="DT-C10-022",
            stage=1,
            trigger_type="question",
            output_mode="fixed",
            response_text="기존에 저장된 다른 대사",
            condition_key="existing_condition",
            output_order=1,
            is_active=False,
        )

        self.write_source()

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(
            NPCDialogueTrigger.objects.count(),
            1,
        )

        self.assertFalse(
            NPCDialogueTrigger.objects.filter(
                trigger_id="DT-C01-001"
            ).exists()
        )

    def test_invalid_trigger_type_rejected(self):
        """허용되지 않은 트리거 유형을 거부합니다."""
        self.write_source(invalid_type=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(
            NPCDialogueTrigger.objects.count(),
            0,
        )


class EvidenceLinkImportTests(TestCase):
    """증거 연결 Import의 무결성 및 안전성을 검증합니다."""

    COLUMNS = [
        "from_evidence",
        "to_evidence",
        "relationship",
        "resulting_inference",
        "unlock_event",
        "needs_canon_approval",
        "presentation_mode",
        "note",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="EvidenceLink Import 테스트",
            status=Case.Status.DRAFT,
        )

        Evidence.objects.bulk_create([
            Evidence(
                case=cls.case,
                evidence_id=f"E{number:02d}",
                name=f"테스트 증거 {number}",
                score=0,
            )
            for number in range(1, 31)
        ])

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source = (
            Path(self.temp_dir.name) / "evidence_links.csv"
        )

    def write_source(self, *, invalid_reference=False):
        """23건의 증거 연결 CSV를 생성합니다."""

        with self.source.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.COLUMNS,
            )
            writer.writeheader()

            for number in range(1, 24):
                source_id = f"E{number:02d}"

                target_id = (
                    "E99"
                    if invalid_reference and number == 23
                    else f"E{number + 1:02d}"
                )

                writer.writerow({
                    "from_evidence": source_id,
                    "to_evidence": target_id,
                    "relationship": "supports",
                    "resulting_inference": f"INF-{number:02d}",
                    "unlock_event": f"EVT-{number:02d}",
                    "needs_canon_approval": "YES",
                    "presentation_mode": "복수(2개)",
                    "note": "",
                })

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_evidence_links",
            source=self.source,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run에서는 DB에 관계가 저장되지 않습니다."""
        self.write_source()

        result = self.run_import()

        self.assertIn("New links: 23", result)
        self.assertIn("DRY RUN", result)
        self.assertEqual(EvidenceLink.objects.count(), 0)

    def test_apply_is_idempotent_and_inactive(self):
        """중복 생성 없이 모든 관계를 비활성 상태로 유지합니다."""
        self.write_source()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New links: 23", first)
        self.assertIn("New links: 0", second)
        self.assertIn("Existing links: 23", second)

        links = list(
            EvidenceLink.objects.select_related(
                "from_evidence",
                "to_evidence",
            )
        )

        self.assertEqual(len(links), 23)

        for link in links:
            self.assertEqual(
                link.from_evidence.case_id,
                self.case.pk,
            )
            self.assertEqual(
                link.to_evidence.case_id,
                self.case.pk,
            )
            self.assertTrue(link.needs_canon_approval)
            self.assertFalse(link.is_active)
            self.assertIs(
                link.metadata["runtime_enabled"],
                False,
            )
            self.assertIs(
                link.metadata["canon_approved"],
                False,
            )

    def test_existing_conflict_rolls_back_all(self):
        """마지막 관계에서 충돌하면 앞선 생성도 롤백합니다."""
        source = Evidence.objects.get(
            case=self.case,
            evidence_id="E23",
        )
        target = Evidence.objects.get(
            case=self.case,
            evidence_id="E24",
        )

        EvidenceLink.objects.create(
            from_evidence=source,
            to_evidence=target,
            relationship="supports",
            resulting_inference="DIFFERENT-INFERENCE",
            needs_canon_approval=True,
            is_active=False,
        )

        self.write_source()

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        # 기존 관계 한 건만 남아 있어야 합니다.
        self.assertEqual(EvidenceLink.objects.count(), 1)

        existing = EvidenceLink.objects.get()
        self.assertEqual(
            existing.resulting_inference,
            "DIFFERENT-INFERENCE",
        )

    def test_unknown_evidence_rejected(self):
        """DB에 없는 증거를 참조하면 전체 Import를 거부합니다."""
        self.write_source(invalid_reference=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(EvidenceLink.objects.count(), 0)

class CharacterRelationshipImportTests(TestCase):
    """인물 관계 Import의 멱등성과 안전성을 검증합니다."""

    COLUMNS = [
        "from_type",
        "from_id",
        "to_type",
        "to_id",
        "relationship",
        "public_from_stage",
        "source_basis",
        "period",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="인물 관계 Import 테스트",
            status=Case.Status.DRAFT,
        )

        for number in range(1, 11):
            Character.objects.create(
                case=cls.case,
                character_id=f"C{number:02d}",
                name=f"NPC {number}",
            )

        for number in range(1, 31):
            Evidence.objects.create(
                case=cls.case,
                evidence_id=f"E{number:02d}",
                name=f"증거 {number}",
                score=0,
            )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source = (
            Path(self.temp_dir.name) / "relationships.csv"
        )

    def write_source(self, *, invalid_evidence=False):
        """원본과 동일한 유형·단계 분포의 58건을 생성합니다."""

        with self.source.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(
                file, fieldnames=self.COLUMNS
            )
            writer.writeheader()

            for index in range(1, 59):
                npc_number = (index - 1) % 10 + 1
                source_id = f"C{npc_number:02d}"

                if index <= 11:
                    target_type = "npc"
                    target_id = f"C{npc_number % 10 + 1:02d}"
                elif index <= 45:
                    target_type = "evidence"
                    evidence_number = (index - 12) % 30 + 1
                    target_id = f"E{evidence_number:02d}"
                else:
                    target_type = "person"
                    target_id = f"P-{index % 2 + 1:02d}"

                if invalid_evidence and index == 45:
                    target_id = "E99"

                if index <= 12:
                    stage = "S1"
                elif index <= 43:
                    stage = "S2"
                else:
                    stage = "S3"

                writer.writerow({
                    "from_type": "npc",
                    "from_id": source_id,
                    "to_type": target_type,
                    "to_id": target_id,
                    "relationship": f"테스트 관계 {index:02d}",
                    "public_from_stage": stage,
                    "source_basis": "test_fixture",
                    "period": "2026",
                })

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_relationships",
            source=self.source,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run 시 실제 DB에 저장하지 않습니다."""
        self.write_source()

        output = self.run_import()

        self.assertIn("New relationships: 58", output)
        self.assertIn("DRY RUN", output)
        self.assertEqual(
            CharacterRelationship.objects.count(), 0
        )

    def test_apply_is_idempotent_and_inactive(self):
        """반복 실행해도 58건을 유지하고 비활성화합니다."""
        self.write_source()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New relationships: 58", first)
        self.assertIn("New relationships: 0", second)
        self.assertIn("Existing relationships: 58", second)

        relations = list(
            CharacterRelationship.objects.all()
        )

        self.assertEqual(len(relations), 58)

        from collections import Counter

        self.assertEqual(
            Counter(r.target_type for r in relations),
            {"npc": 11, "evidence": 34, "person": 13},
        )

        self.assertEqual(
            Counter(r.public_from_stage for r in relations),
            {1: 12, 2: 31, 3: 15},
        )

        for relation in relations:
            self.assertFalse(relation.is_active)
            self.assertIs(
                relation.metadata["runtime_enabled"], False
            )
            self.assertIs(
                relation.metadata["canon_approved"], False
            )

    def test_existing_conflict_rolls_back_all(self):
        """마지막 행에서 충돌하면 앞선 57건도 롤백합니다."""
        self.write_source()

        character = Character.objects.get(
            case=self.case,
            character_id="C08",
        )

        CharacterRelationship.objects.create(
            source_character=character,
            target_type="person",
            target_id="P-01",
            relationship="기존에 저장된 다른 관계",
            public_from_stage=3,
            is_active=False,
            metadata={
                "import_source": "case001_1120",
                "import_dataset": "relationships",
                "source_line": 59,
            },
        )

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(
            CharacterRelationship.objects.count(), 1
        )

        existing = CharacterRelationship.objects.get()
        self.assertEqual(
            existing.relationship,
            "기존에 저장된 다른 관계",
        )

    def test_unknown_evidence_rejected(self):
        """존재하지 않는 증거 참조를 차단합니다."""
        self.write_source(invalid_evidence=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(
            CharacterRelationship.objects.count(), 0
        )


class ObjectiveImportTests(TestCase):
    """Objective Import의 데이터 무결성과 안전 정책을 검증합니다."""

    COLUMNS = [
        "objective_id",
        "unlocked_by_evidence",
        "target_evidence",
        "chapter",
        "player_goal",
        "trigger_source",
        "hint_1",
        "hint_2",
        "hint_3",
        "wrong_feedback",
        "completion",
        "status",
    ]

    CHAPTER_COUNTS = {
        "CH00": 2,
        "CH01": 5,
        "CH02": 8,
        "CH03": 7,
        "CH04": 3,
    }

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="Objective Import 테스트",
            status=Case.Status.DRAFT,
        )

        for number in range(5):
            Chapter.objects.create(
                case=cls.case,
                code=f"CH{number:02d}",
                order=number,
                title=f"챕터 {number}",
            )

        for number in range(1, 31):
            Evidence.objects.create(
                case=cls.case,
                evidence_id=f"E{number:02d}",
                name=f"테스트 증거 {number}",
                score=0,
            )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.source = (
            Path(self.temp_dir.name) / "objectives.csv"
        )

    def write_source(self, *, invalid_evidence=False):
        """챕터 분포와 특수 목표가 포함된 25건의 CSV를 생성합니다."""

        index = 0

        with self.source.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.COLUMNS,
            )
            writer.writeheader()

            for chapter, count in self.CHAPTER_COUNTS.items():
                for _ in range(count):
                    index += 1

                    objective_id = f"OBJ_{index:03d}"
                    target = f"E{index:02d}"
                    unlock = (
                        ""
                        if index <= 3
                        else f"E{index - 1:02d}"
                    )

                    if index == 24:
                        objective_id = "OBJ_FINAL_RECONSTRUCTION"
                        target = "FINAL"
                        unlock = "E29"

                    elif index == 25:
                        objective_id = "OBJ_COMPLETE_OLD_CASE"
                        target = "DEEP"
                        unlock = "E30"

                    if invalid_evidence and index == 23:
                        target = "E99"

                    writer.writerow({
                        "objective_id": objective_id,
                        "unlocked_by_evidence": unlock,
                        "target_evidence": target,
                        "chapter": chapter,
                        "player_goal": f"플레이어 목표 {index}",
                        "trigger_source": "test_fixture",
                        "hint_1": f"첫 번째 힌트 {index}",
                        "hint_2": f"두 번째 힌트 {index}",
                        "hint_3": f"세 번째 힌트 {index}",
                        "wrong_feedback": "다시 조사해 보세요.",
                        "completion": "미승인 완료 조건",
                        "status": "초안",
                    })

    def run_import(self, *, apply=False):
        output = StringIO()

        call_command(
            "import_case001_objectives",
            source=self.source,
            apply=apply,
            stdout=output,
        )

        return output.getvalue()

    def test_dry_run_rolls_back(self):
        """Dry Run 시 실제 DB에 저장하지 않습니다."""
        self.write_source()

        result = self.run_import()

        self.assertIn("New objectives: 25", result)
        self.assertIn("DRY RUN", result)
        self.assertEqual(Objective.objects.count(), 0)

    def test_apply_is_idempotent_and_inactive(self):
        """반복 Import 후에도 25건과 비활성 정책을 유지합니다."""
        self.write_source()

        first = self.run_import(apply=True)
        second = self.run_import(apply=True)

        self.assertIn("New objectives: 25", first)
        self.assertIn("New objectives: 0", second)
        self.assertIn("Existing objectives: 25", second)

        objectives = list(
            Objective.objects.select_related("chapter")
        )

        self.assertEqual(len(objectives), 25)

        from collections import Counter

        self.assertEqual(
            Counter(obj.chapter.code for obj in objectives),
            self.CHAPTER_COUNTS,
        )

        for obj in objectives:
            self.assertEqual(len(obj.hints), 3)
            self.assertEqual(obj.completion_rule, {})
            self.assertFalse(obj.is_active)
            self.assertIs(
                obj.metadata["runtime_enabled"],
                False,
            )
            self.assertIs(
                obj.metadata["completion_rule_approved"],
                False,
            )

        special = {
            obj.objective_id: obj.metadata["source_target_evidence"]
            for obj in objectives
            if obj.metadata["source_target_type"] == "symbolic"
        }

        self.assertEqual(
            special,
            {
                "OBJ_FINAL_RECONSTRUCTION": "FINAL",
                "OBJ_COMPLETE_OLD_CASE": "DEEP",
            },
        )

    def test_existing_conflict_rolls_back_all(self):
        """마지막 Objective 충돌 시 이전 생성 내역도 롤백합니다."""
        self.write_source()

        chapter = Chapter.objects.get(
            case=self.case,
            code="CH04",
        )

        Objective.objects.create(
            chapter=chapter,
            objective_id="OBJ_COMPLETE_OLD_CASE",
            player_goal="기존에 저장된 다른 목표",
            hints=["기존 힌트"],
            completion_rule={},
            is_active=False,
        )

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        # 신규 생성 예정이던 24건도 롤백되어야 합니다.
        self.assertEqual(Objective.objects.count(), 1)

        existing = Objective.objects.get()
        self.assertEqual(
            existing.player_goal,
            "기존에 저장된 다른 목표",
        )

        self.assertFalse(
            Objective.objects.filter(
                objective_id="OBJ_001"
            ).exists()
        )

    def test_unknown_evidence_rejected(self):
        """존재하지 않는 증거 참조를 차단합니다."""
        self.write_source(invalid_evidence=True)

        with self.assertRaises(CommandError):
            self.run_import(apply=True)

        self.assertEqual(Objective.objects.count(), 0)
