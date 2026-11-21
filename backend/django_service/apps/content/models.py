
"""추리 게임 콘텐츠 관리용 Django ORM 모델."""

from django.core.validators import RegexValidator
from django.db import models
from django.core.exceptions import ValidationError

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


class Evidence(models.Model):
    """사건별 증거 정의와 관련 NPC 및 획득 규칙을 관리합니다."""

    case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        related_name="evidence_items",
        verbose_name="소속 사건",
    )

    evidence_id = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^E(0[1-9]|[12][0-9]|30)$",
                message="증거 ID는 E01~E30 형식이어야 합니다.",
            )
        ],
        verbose_name="증거 ID",
    )

    name = models.CharField(
        max_length=200,
        verbose_name="증거 이름",
    )

    holder = models.ForeignKey(
        Character,
        on_delete=models.PROTECT,
        related_name="held_evidence",
        null=True,
        blank=True,
        verbose_name="관련 NPC",
    )

    score = models.PositiveIntegerField(
        default=0,
        verbose_name="증거 점수",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="내부 증거 메타데이터",
    )

    prerequisites = models.ManyToManyField(
        "self",
        through="EvidencePrerequisite",
        through_fields=("dependent", "prerequisite"),
        symmetrical=False,
        related_name="required_by",
        blank=True,
        verbose_name="선행 증거",
    )

    def clean(self):
        """관련 NPC와 증거가 동일한 사건에 속하는지 검증합니다."""
        super().clean()

        if self.case_id is None or self.holder_id is None:
            return

        if not Character.objects.filter(
            pk=self.holder_id,
            case_id=self.case_id,
        ).exists():
            raise ValidationError({
                "holder": "관련 NPC는 증거와 동일한 사건에 속해야 합니다."
            })

    class Meta:
        db_table = "content_evidence"
        verbose_name = "증거"
        verbose_name_plural = "증거 목록"
        ordering = ["case", "evidence_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "evidence_id"],
                name="unique_evidence_case_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.evidence_id} - {self.name}"


class EvidencePrerequisite(models.Model):
    """증거 간 선행 관계와 참조 무결성을 관리합니다."""

    dependent = models.ForeignKey(
        Evidence,
        on_delete=models.PROTECT,
        related_name="prerequisite_edges",
        verbose_name="후행 증거",
    )

    prerequisite = models.ForeignKey(
        Evidence,
        on_delete=models.PROTECT,
        related_name="dependent_edges",
        verbose_name="선행 증거",
    )

    def clean(self):
        """자기참조, 교차 사건 참조, 순환 관계를 검증합니다."""
        super().clean()

        if self.dependent_id is None or self.prerequisite_id is None:
            return

        if self.dependent_id == self.prerequisite_id:
            raise ValidationError({
                "prerequisite": "증거는 자기 자신을 선행 조건으로 가질 수 없습니다."
            })

        # 두 증거가 동일한 사건에 속하는지 확인합니다.
        cases = dict(
            Evidence.objects.filter(
                pk__in=[self.dependent_id, self.prerequisite_id]
            ).values_list("pk", "case_id")
        )

        if len(cases) != 2:
            return

        case_id = cases[self.dependent_id]

        if case_id != cases[self.prerequisite_id]:
            raise ValidationError({
                "prerequisite": "서로 다른 사건의 증거를 연결할 수 없습니다."
            })

        # 새로운 관계를 추가했을 때 순환 경로가 생성되는지 검사합니다.
        # 기존 관계 수정 시 현재 레코드는 탐색에서 제외합니다.
        edges = (
            EvidencePrerequisite.objects
            .filter(dependent__case_id=case_id)
            .exclude(pk=self.pk)
            .values_list("dependent_id", "prerequisite_id")
        )

        graph = {}
        for dependent_id, prerequisite_id in edges:
            graph.setdefault(dependent_id, set()).add(prerequisite_id)

        visited = set()
        pending = [self.prerequisite_id]

        while pending:
            current = pending.pop()

            if current == self.dependent_id:
                raise ValidationError({
                    "prerequisite": "선행 증거 관계에 순환 참조가 발생합니다."
                })

            if current in visited:
                continue

            visited.add(current)
            pending.extend(graph.get(current, ()))

    class Meta:
        db_table = "content_evidence_prerequisite"
        verbose_name = "증거 선행 관계"
        verbose_name_plural = "증거 선행 관계 목록"
        constraints = [
            models.UniqueConstraint(
                fields=["dependent", "prerequisite"],
                name="unique_evidence_prerequisite",
            ),
            models.CheckConstraint(
                condition=~models.Q(
                    dependent=models.F("prerequisite")
                ),
                name="evidence_prereq_no_self",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.dependent.evidence_id} "
            f"requires {self.prerequisite.evidence_id}"
        )


class StoryEvent(models.Model):
    """챕터별 스토리 이벤트의 조건과 출력 콘텐츠를 관리합니다."""

    class TriggerType(models.TextChoices):
        EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED", "증거 획득"
        NPC_UNLOCKED = "NPC_UNLOCKED", "NPC 해금"
        CHAPTER_STARTED = "CHAPTER_STARTED", "챕터 시작"
        DIALOGUE_COMPLETED = "DIALOGUE_COMPLETED", "대화 완료"

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        related_name="story_events",
        verbose_name="소속 챕터",
    )

    event_key = models.CharField(
        max_length=100,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^EVT-CH0[0-4]-\d{3}$",
                message="이벤트 키는 EVT-CH01-001 형식이어야 합니다.",
            )
        ],
        verbose_name="이벤트 키",
    )

    trigger_type = models.CharField(
        max_length=50,
        choices=TriggerType.choices,
        verbose_name="트리거 유형",
    )

    conditions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="발동 조건",
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="이벤트 콘텐츠",
    )

    def clean(self):
        """JSON 객체 구조와 챕터 식별자의 일관성을 검증합니다."""
        super().clean()

        errors = {}

        if not isinstance(self.conditions, dict):
            errors["conditions"] = "발동 조건은 JSON 객체여야 합니다."

        if not isinstance(self.payload, dict):
            errors["payload"] = "이벤트 콘텐츠는 JSON 객체여야 합니다."

        if self.chapter_id and self.event_key:
            chapter_code = (
                Chapter.objects.filter(pk=self.chapter_id)
                .values_list("code", flat=True)
                .first()
            )

            if chapter_code and not self.event_key.startswith(
                f"EVT-{chapter_code}-"
            ):
                errors["event_key"] = (
                    "이벤트 키의 챕터 코드가 소속 챕터와 일치해야 합니다."
                )

        if errors:
            raise ValidationError(errors)

    class Meta:
        db_table = "content_storyevent"
        verbose_name = "스토리 이벤트"
        verbose_name_plural = "스토리 이벤트 목록"
        ordering = ["chapter", "event_key"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    trigger_type__in=[
                        "EVIDENCE_COLLECTED",
                        "NPC_UNLOCKED",
                        "CHAPTER_STARTED",
                        "DIALOGUE_COMPLETED",
                    ]
                ),
                name="storyevent_valid_trigger",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_key} - {self.trigger_type}"
