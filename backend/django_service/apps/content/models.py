
"""추리 게임 콘텐츠 관리용 Django ORM 모델."""

from django.core.validators import RegexValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

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


class Scene(models.Model):
    """사건별 스토리 장면과 공개 조건을 관리합니다."""

    class Visibility(models.TextChoices):
        ENGINE_ONLY = "ENGINE_ONLY", "서버 전용"
        NPC_KNOWLEDGE = "NPC_KNOWLEDGE", "NPC 전용"
        UNLOCKED_ONLY = "UNLOCKED_ONLY", "해금 후 공개"
        PLAYER_VISIBLE = "PLAYER_VISIBLE", "기본 공개"

    case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        related_name="scenes",
        verbose_name="소속 사건",
    )

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.PROTECT,
        related_name="scenes",
        verbose_name="소속 챕터",
    )

    scene_id = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^SC-\d{4}$",
                message="장면 ID는 SC-0001 형식이어야 합니다.",
            ),
        ],
        verbose_name="장면 ID",
    )

    title = models.CharField(
        max_length=200,
        verbose_name="장면 제목",
    )

    scene_text = models.TextField(
        verbose_name="장면 원고",
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.UNLOCKED_ONLY,
        verbose_name="공개 수준",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="장면 메타데이터",
    )

    def clean(self):
        """챕터 소속과 메타데이터 구조를 검증합니다."""
        super().clean()

        errors = {}

        if self.case_id and self.chapter_id:
            if Chapter.objects.filter(
                pk=self.chapter_id
            ).exclude(case_id=self.case_id).exists():
                errors["chapter"] = (
                    "장면과 챕터는 동일한 사건에 속해야 합니다."
                )

        if not isinstance(self.metadata, dict):
            errors["metadata"] = (
                "장면 메타데이터는 JSON 객체여야 합니다."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """ORM 저장 시에도 모델 유효성 검사를 수행합니다."""
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "content_scene"
        verbose_name = "스토리 장면"
        verbose_name_plural = "스토리 장면 목록"
        ordering = ["chapter__order", "scene_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "scene_id"],
                name="unique_scene_case_id",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    visibility__in=[
                        "ENGINE_ONLY",
                        "NPC_KNOWLEDGE",
                        "UNLOCKED_ONLY",
                        "PLAYER_VISIBLE",
                    ]
                ),
                name="scene_valid_visibility",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.scene_id} - {self.title}"


class NPCCard(models.Model):
    """NPC의 지식 카드와 잡담 카드를 관리합니다."""

    class CardType(models.TextChoices):
        KNOWLEDGE = "KNOWLEDGE", "지식 카드"
        SMALLTALK = "SMALLTALK", "잡담 카드"

    character = models.ForeignKey(
        "Character",
        on_delete=models.PROTECT,
        related_name="cards",
        verbose_name="소속 NPC",
    )

    card_id = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r"^K-C(0[1-9]|10)-(?:[0-9]{2}|S[0-9]{2})$",
                message="카드 ID는 K-C01-01 또는 K-C01-S01 형식이어야 합니다.",
            )
        ],
        verbose_name="카드 ID",
    )

    card_type = models.CharField(
        max_length=20,
        choices=CardType.choices,
        verbose_name="카드 유형",
    )

    content = models.TextField(
        verbose_name="카드 내용",
    )

    disclosure_policy = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="공개 조건",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="카드 메타데이터",
    )

    def clean(self):
        """NPC 소속, 카드 유형 및 JSON 구조를 검증합니다."""
        super().clean()

        errors = {}

        if not isinstance(self.disclosure_policy, dict):
            errors["disclosure_policy"] = (
                "공개 조건은 JSON 객체여야 합니다."
            )

        if not isinstance(self.metadata, dict):
            errors["metadata"] = (
                "메타데이터는 JSON 객체여야 합니다."
            )

        if self.card_id:
            suffix = self.card_id.rsplit("-", 1)[-1]

            if self.card_type == self.CardType.KNOWLEDGE:
                if suffix.startswith("S"):
                    errors["card_id"] = (
                        "지식 카드에는 일반 카드 ID를 사용해야 합니다."
                    )

            elif self.card_type == self.CardType.SMALLTALK:
                if not suffix.startswith("S"):
                    errors["card_id"] = (
                        "잡담 카드 ID에는 S 접두사가 필요합니다."
                    )

        if self.character_id and self.card_id:
            npc_id = Character.objects.filter(
                pk=self.character_id,
            ).values_list(
                "character_id", flat=True
            ).first()

            if npc_id and not self.card_id.startswith(
                f"K-{npc_id}-"
            ):
                errors["card_id"] = (
                    "카드 ID와 소속 NPC의 ID가 일치해야 합니다."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """저장 전 카드의 유효성을 검사합니다."""
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "content_npc_card"
        verbose_name = "NPC 카드"
        verbose_name_plural = "NPC 카드 목록"
        ordering = ["character__character_id", "card_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["character", "card_id"],
                name="unique_npc_card_character_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.card_id} - {self.get_card_type_display()}"


class NPCDialogueTrigger(models.Model):
    """NPC 대화 트리거와 고정·참고 대사를 관리합니다."""

    class TriggerType(models.TextChoices):
        QUESTION = "question", "일반 질문"
        VERBAL_ONLY = "verbal_only", "증거 없는 대화"
        EVIDENCE = "evidence", "단일 증거"
        EVIDENCE_COMBO = "evidence_combo", "증거 조합"

    class OutputMode(models.TextChoices):
        FIXED = "fixed", "고정 대사"
        REFERENCE = "reference", "참고 대사"

    character = models.ForeignKey(
        "Character",
        on_delete=models.PROTECT,
        related_name="dialogue_triggers",
        verbose_name="소속 NPC",
    )

    trigger_id = models.CharField(
        max_length=20,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^DT-C(0[1-9]|10)-\d{3}$",
                message="트리거 ID는 DT-C01-001 형식이어야 합니다.",
            )
        ],
        verbose_name="대화 트리거 ID",
    )

    stage = models.PositiveSmallIntegerField(
        verbose_name="NPC 대화 단계",
    )

    trigger_type = models.CharField(
        max_length=30,
        choices=TriggerType.choices,
        verbose_name="트리거 유형",
    )

    output_mode = models.CharField(
        max_length=20,
        choices=OutputMode.choices,
        verbose_name="대사 출력 방식",
    )

    response_text = models.TextField(
        verbose_name="대사 원문",
    )

    condition_key = models.CharField(
        max_length=100,
        verbose_name="발동 조건 키",
    )

    output_order = models.PositiveIntegerField(
        default=1,
        verbose_name="출력 순서",
    )

    is_active = models.BooleanField(
        default=False,
        verbose_name="활성화 여부",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="대화 메타데이터",
    )

    def clean(self):
        """NPC 소속, 단계 및 메타데이터 구조를 검증합니다."""
        super().clean()

        errors = {}

        if self.stage is not None and self.stage not in (1, 2, 3):
            errors["stage"] = "대화 단계는 1~3이어야 합니다."

        if self.output_order is not None and self.output_order < 1:
            errors["output_order"] = (
                "출력 순서는 1 이상이어야 합니다."
            )

        if not isinstance(self.metadata, dict):
            errors["metadata"] = (
                "대화 메타데이터는 JSON 객체여야 합니다."
            )

        if self.character_id and self.trigger_id:
            npc_id = self.character.__class__.objects.filter(
                pk=self.character_id
            ).values_list(
                "character_id", flat=True
            ).first()

            if npc_id and not self.trigger_id.startswith(
                f"DT-{npc_id}-"
            ):
                errors["trigger_id"] = (
                    "트리거 ID와 소속 NPC가 일치해야 합니다."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """저장 전 대화 트리거의 유효성을 검증합니다."""
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "content_npc_dialogue_trigger"
        verbose_name = "NPC 대화 트리거"
        verbose_name_plural = "NPC 대화 트리거 목록"

        ordering = [
            "character__character_id",
            "stage",
            "output_order",
            "trigger_id",
        ]

        indexes = [
            models.Index(
                fields=["character", "stage", "trigger_type"],
                name="npc_trigger_lookup_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(stage__gte=1, stage__lte=3),
                name="npc_trigger_valid_stage",
            ),
            models.CheckConstraint(
                condition=models.Q(output_order__gte=1),
                name="npc_trigger_valid_order",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.trigger_id} - "
            f"{self.
            get_output_mode_display()}"
        )


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


class EvidenceLink(models.Model):
    """증거 간 추론 및 연관 관계를 관리합니다."""

    from_evidence = models.ForeignKey(
        "Evidence",
        on_delete=models.PROTECT,
        related_name="outgoing_links",
        verbose_name="출발 증거",
    )

    to_evidence = models.ForeignKey(
        "Evidence",
        on_delete=models.PROTECT,
        related_name="incoming_links",
        verbose_name="연결 증거",
    )

    relationship = models.CharField(
        max_length=100,
        verbose_name="추론 관계 유형",
    )

    resulting_inference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="도출되는 추론 ID",
    )

    needs_canon_approval = models.BooleanField(
        default=True,
        verbose_name="정본 승인 필요",
    )

    is_active = models.BooleanField(
        default=False,
        verbose_name="게임 적용 여부",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="추론 관계 메타데이터",
    )

    def clean(self):
        """증거 관계의 참조 무결성과 승인 상태를 검증합니다."""
        super().clean()

        errors = {}

        if self.from_evidence_id and self.to_evidence_id:
            if self.from_evidence_id == self.to_evidence_id:
                errors["to_evidence"] = (
                    "증거는 자기 자신과 연결할 수 없습니다."
                )
            else:
                evidence_cases = dict(
                    Evidence.objects.filter(
                        pk__in=[
                            self.from_evidence_id,
                            self.to_evidence_id,
                        ]
                    ).values_list("pk", "case_id")
                )

                from_case = evidence_cases.get(
                    self.from_evidence_id
                )
                to_case = evidence_cases.get(
                    self.to_evidence_id
                )

                if (
                    from_case is not None
                    and to_case is not None
                    and from_case != to_case
                ):
                    errors["to_evidence"] = (
                        "같은 사건에 속한 증거만 연결할 수 있습니다."
                    )

        if not isinstance(self.metadata, dict):
            errors["metadata"] = (
                "메타데이터는 JSON 객체여야 합니다."
            )

        if self.is_active and self.needs_canon_approval:
            errors["is_active"] = (
                "정본 승인이 필요한 추론 관계는 "
                "활성화할 수 없습니다."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """저장 전 추론 관계의 유효성을 검증합니다."""
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "content_evidence_link"
        verbose_name = "증거 추론 관계"
        verbose_name_plural = "증거 추론 관계 목록"

        ordering = [
            "from_evidence__evidence_id",
            "to_evidence__evidence_id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "from_evidence",
                    "to_evidence",
                    "relationship",
                ],
                name="unique_evidence_link_relation",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=False)
                    | models.Q(needs_canon_approval=False)
                ),
                name="evidence_link_approval_required",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.from_evidence.evidence_id} → "
            f"{self.to_evidence.evidence_id} "
            f"({self.relationship})"
        )


class CharacterRelationship(models.Model):
    """NPC와 다른 NPC·증거·외부 인물 간 관계를 관리합니다."""

    class TargetType(models.TextChoices):
        NPC = "npc", "NPC"
        EVIDENCE = "evidence", "증거"
        PERSON = "person", "외부 인물"

    source_character = models.ForeignKey(
        "Character",
        on_delete=models.PROTECT,
        related_name="outgoing_relationships",
        verbose_name="출발 NPC",
    )

    target_type = models.CharField(
        max_length=20,
        choices=TargetType.choices,
        verbose_name="관계 대상 유형",
    )

    target_id = models.CharField(
        max_length=100,
        verbose_name="관계 대상 ID",
    )

    relationship = models.TextField(
        verbose_name="관계 설명",
    )

    public_from_stage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="최소 공개 단계",
    )

    is_active = models.BooleanField(
        default=False,
        verbose_name="활성화 여부",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="관계 메타데이터",
    )

    def clean(self):
        """관계 대상, 사건 일치 여부 및 공개 조건을 검증합니다."""
        super().clean()

        errors = {}

        if not isinstance(self.metadata, dict):
            errors["metadata"] = (
                "관계 메타데이터는 JSON 객체여야 합니다."
            )

        if (
            self.public_from_stage is not None
            and self.public_from_stage not in (1, 2, 3)
        ):
            errors["public_from_stage"] = (
                "공개 단계는 1~3이어야 합니다."
            )

        if self.is_active and self.public_from_stage is None:
            errors["is_active"] = (
                "공개 단계가 확정되지 않은 관계는 "
                "활성화할 수 없습니다."
            )

        if not self.target_id or not self.target_id.strip():
            errors["target_id"] = (
                "관계 대상 ID를 입력해야 합니다."
            )

        if self.source_character_id and self.target_id:
            case_id = Character.objects.filter(
                pk=self.source_character_id
            ).values_list(
                "case_id", flat=True
            ).first()

            if case_id is not None:
                if self.target_type == self.TargetType.NPC:
                    exists = Character.objects.filter(
                        case_id=case_id,
                        character_id=self.target_id,
                    ).exists()

                    if not exists:
                        errors["target_id"] = (
                            "같은 사건에 소속된 NPC만 "
                            "관계 대상으로 지정할 수 있습니다."
                        )

                elif self.target_type == self.TargetType.EVIDENCE:
                    exists = Evidence.objects.filter(
                        case_id=case_id,
                        evidence_id=self.target_id,
                    ).exists()

                    if not exists:
                        errors["target_id"] = (
                            "같은 사건에 소속된 증거만 "
                            "관계 대상으로 지정할 수 있습니다."
                        )

                # 외부 인물(person)은 아직 전용 모델이 없으므로
                # 원본 식별자를 보존하고 상세 검증은 Import에서 수행합니다.

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """저장 전 관계 무결성을 검증합니다."""
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "content_character_relationship"
        verbose_name = "인물 관계"
        verbose_name_plural = "인물 관계 목록"

        ordering = [
            "source_character__character_id",
            "target_type",
            "target_id",
        ]

        indexes = [
            models.Index(
                fields=["source_character", "target_type"],
                name="npc_relation_lookup_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    target_type__in=["npc", "evidence", "person"]
                ),
                name="npc_relation_valid_target",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(public_from_stage__isnull=True)
                    | models.Q(
                        public_from_stage__gte=1,
                        public_from_stage__lte=3,
                    )
                ),
                name="npc_relation_valid_stage",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=False)
                    | models.Q(public_from_stage__isnull=False)
                ),
                name="npc_relation_active_stage",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.source_character.character_id} → "
            f"{self.target_type}:{self.target_id}"
        )


class Objective(models.Model):
    """플레이어 목표와 단계별 힌트를 관리합니다."""

    chapter = models.ForeignKey(
        "Chapter",
        on_delete=models.PROTECT,
        related_name="objectives",
        verbose_name="소속 챕터",
    )

    objective_id = models.CharField(
        max_length=64,
        validators=[
            RegexValidator(
                regex=r"^OBJ_(?:\d{3}|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*)$",
                message=(
                    "목표 ID는 OBJ_001 또는 "
                    "OBJ_FIND_STUDENT_RECORD 형식이어야 합니다."
                ),
            ),
        ],
        verbose_name="목표 ID",
    )

    player_goal = models.TextField(
        verbose_name="플레이어 목표",
    )

    hints = models.JSONField(
        default=list,
        blank=True,
        verbose_name="단계별 힌트",
    )

    completion_rule = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="목표 완료 조건",
    )

    is_active = models.BooleanField(
        default=False,
        verbose_name="게임 적용 여부",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="목표 메타데이터",
    )

    def clean(self):
        """힌트 구조와 목표 활성화 조건을 검증합니다."""
        super().clean()

        errors = {}

        if not isinstance(self.hints, list):
            errors["hints"] = (
                "힌트는 JSON 배열이어야 합니다."
            )
        elif (
            len(self.hints) > 3
            or any(
                not isinstance(hint, str)
                or not hint.strip()
                for hint in self.hints
            )
        ):
            errors["hints"] = (
                "힌트는 최대 3개의 비어 있지 않은 "
                "문자열이어야 합니다."
            )

        if not isinstance(self.completion_rule, dict):
            errors["completion_rule"] = (
                "완료 조건은 JSON 객체여야 합니다."
            )

        if not isinstance(self.metadata, dict):
            errors["metadata"] = (
                "목표 메타데이터는 JSON 객체여야 합니다."
            )

        if (
            self.is_active
            and (
                not isinstance(self.completion_rule, dict)
                or not self.completion_rule
            )
        ):
            errors["is_active"] = (
                "완료 조건이 정의되지 않은 목표는 "
                "활성화할 수 없습니다."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """저장 전 목표의 유효성을 검증합니다."""
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        db_table = "content_objective"

        verbose_name = "플레이어 목표"
        verbose_name_plural = "플레이어 목표 목록"

        ordering = [
            "chapter__order",
            "objective_id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["chapter", "objective_id"],
                name="unique_objective_chapter_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.objective_id} - {self.player_goal[:30]}"


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


class ContentReleaseQuerySet(models.QuerySet):
    """게시된 콘텐츠의 대량 수정 및 삭제를 차단합니다."""

    def update(self, **kwargs):
        raise ValidationError(
            "ContentRelease의 대량 수정은 허용되지 않습니다."
        )

    def delete(self):
        raise ValidationError(
            "ContentRelease의 대량 삭제는 허용되지 않습니다."
        )

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "ContentRelease의 대량 수정은 허용되지 않습니다."
        )

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        raise ValidationError(
            "ContentRelease의 대량 생성은 허용되지 않습니다. "
            "검증된 단건 생성 경로를 사용해야 합니다."
        )

class ContentRelease(models.Model):
    """사건별 게시 콘텐츠의 버전과 스냅샷을 관리합니다."""
    objects = ContentReleaseQuerySet.as_manager()
    case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        related_name="releases",
        verbose_name="대상 사건",
    )

    version = models.CharField(
        max_length=30,
        validators=[
            RegexValidator(
                regex=r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$",
                message="버전은 v1.0.0 형식이어야 합니다.",
            )
        ],
        verbose_name="게시 버전",
    )

    manifest = models.JSONField(
        verbose_name="콘텐츠 스냅샷",
    )

    checksum = models.CharField(
        max_length=71,
        validators=[
            RegexValidator(
                regex=r"^sha256:[0-9a-f]{64}$",
                message="체크섬은 sha256: + 64자리 소문자 16진수여야 합니다.",
            )
        ],
        verbose_name="SHA-256 체크섬",
    )

    published_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        verbose_name="게시 시각",
    )

    def clean(self):
        """스냅샷의 기본 구조를 검증합니다."""
        super().clean()

        if not isinstance(self.manifest, dict):
            raise ValidationError({
                "manifest": "콘텐츠 스냅샷은 JSON 객체여야 합니다."
            })

    def save(self, *args, **kwargs):
        """최초 생성만 허용하고 게시 후 수정을 거부합니다."""
        if not self._state.adding:
            raise ValidationError(
                "게시된 ContentRelease는 수정할 수 없습니다."
            )

        # PK를 직접 지정하여 기존 행을 덮어쓰는 것도 방지합니다.
        if self.pk is not None and type(self).objects.filter(
            pk=self.pk
        ).exists():
            raise ValidationError(
                "이미 존재하는 ContentRelease는 수정할 수 없습니다."
            )

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """게시된 배포 기록의 개별 삭제를 차단합니다."""
        if self.pk is not None:
            raise ValidationError(
                "게시된 ContentRelease는 삭제할 수 없습니다."
            )

        return super().delete(*args, **kwargs)

    class Meta:
        db_table = "content_contentrelease"
        verbose_name = "콘텐츠 게시 버전"
        verbose_name_plural = "콘텐츠 게시 버전 목록"
        ordering = ["-published_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "version"],
                name="unique_release_case_version",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.case.case_id} - {self.version}"
