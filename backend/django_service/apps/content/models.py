
"""추리 게임 콘텐츠 관리용 Django ORM 모델."""

from django.core.validators import RegexValidator
from django.db import models


class Case(models.Model):
    """게임 사건의 기본 정보를 관리합니다."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "작성 중"
        REVIEW = "REVIEW", "검토 중"
        PUBLISHED = "PUBLISHED", "게시됨"
        ARCHIVED = "ARCHIVED", "보관됨"

    case_id = models.CharField(
        max_length=20,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^CASE-\d{3}$",
                message="사건 ID는 CASE-001 형식이어야 합니다.",
            )
        ],
        verbose_name="사건 ID",
    )

    title = models.CharField(
        max_length=200,
        verbose_name="사건 제목",
    )

    description = models.TextField(
        blank=True,
        verbose_name="공개 사건 소개",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="관리 상태",
    )

    class Meta:
        db_table = "content_case"
        verbose_name = "사건"
        verbose_name_plural = "사건 목록"
        ordering = ["case_id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "DRAFT",
                        "REVIEW",
                        "PUBLISHED",
                        "ARCHIVED",
                    ]
                ),
                name="case_valid_status",
            )
        ]

    def __str__(self) -> str:
        return f"{self.case_id} - {self.title}"


class Chapter(models.Model):
    """사건별 챕터 콘텐츠와 진행 순서를 관리합니다."""

    case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        related_name="chapters",
        verbose_name="소속 사건",
    )

    code = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^CH0[0-4]$",
                message="챕터 코드는 CH00~CH04 형식이어야 합니다.",
            )
        ],
        verbose_name="챕터 코드",
    )

    order = models.PositiveIntegerField(
        verbose_name="챕터 순서",
    )

    title = models.CharField(
        max_length=200,
        verbose_name="챕터 제목",
    )

    summary = models.TextField(
        blank=True,
        verbose_name="챕터 요약",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추가 메타데이터",
    )

    class Meta:
        db_table = "content_chapter"
        verbose_name = "챕터"
        verbose_name_plural = "챕터 목록"
        ordering = ["case", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "code"],
                name="unique_chapter_case_code",
            ),
            models.UniqueConstraint(
                fields=["case", "order"],
                name="unique_chapter_case_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.title}"


class Character(models.Model):
    """사건별 NPC의 공개 프로필과 내부 메타데이터를 관리합니다."""

    case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        related_name="characters",
        verbose_name="소속 사건",
    )

    character_id = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^C(0[1-9]|10)$",
                message="NPC ID는 C01~C10 형식이어야 합니다.",
            )
        ],
        verbose_name="NPC ID",
    )

    name = models.CharField(
        max_length=100,
        verbose_name="NPC 이름",
    )

    profile = models.TextField(
        blank=True,
        verbose_name="공개 프로필",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="내부 메타데이터",
    )

    class Meta:
        db_table = "content_character"
        verbose_name = "인물"
        verbose_name_plural = "인물 목록"
        ordering = ["case", "character_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "character_id"],
                name="unique_character_case_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_id} - {self.name}"
