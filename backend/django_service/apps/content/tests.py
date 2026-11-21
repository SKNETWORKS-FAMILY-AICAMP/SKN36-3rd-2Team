
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
)
from django.db.models.deletion import ProtectedError
from .models import ContentRelease
from django.contrib.auth import get_user_model
from django.urls import reverse

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
