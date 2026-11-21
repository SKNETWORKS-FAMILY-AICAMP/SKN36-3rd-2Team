
"""Django 콘텐츠 핵심 ORM 모델 테스트."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Case, Chapter, Character


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
