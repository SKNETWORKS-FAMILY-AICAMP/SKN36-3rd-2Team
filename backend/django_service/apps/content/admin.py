
"""추리 게임 콘텐츠 관리용 Django Admin 설정."""

from django.contrib import admin

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

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    """사건 목록, 검색, 상태 필터 및 수정 화면."""

    list_display = (
        "case_id",
        "title",
        "status",
    )

    list_display_links = ("case_id", "title")

    search_fields = (
        "case_id",
        "title",
        "description",
    )

    list_filter = ("status",)

    ordering = ("case_id",)

    list_per_page = 25

    fields = (
        "case_id",
        "title",
        "description",
        "status",
    )


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    """사건별 챕터 검색, 정렬 및 콘텐츠 관리."""

    list_display = (
        "code",
        "title",
        "case",
        "order",
    )

    list_display_links = ("code", "title")

    search_fields = (
        "code",
        "title",
        "summary",
        "case__case_id",
        "case__title",
    )

    list_filter = ("case",)

    ordering = ("case__case_id", "order")

    list_select_related = ("case",)

    autocomplete_fields = ("case",)

    list_per_page = 25

    fields = (
        "case",
        "code",
        "order",
        "title",
        "summary",
        "metadata",
    )


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    """NPC의 공개 프로필과 내부 메타데이터를 관리합니다."""

    list_display = (
        "character_id",
        "name",
        "case",
    )

    list_display_links = ("character_id", "name")

    search_fields = (
        "character_id",
        "name",
        "profile",
        "case__case_id",
        "case__title",
    )

    list_filter = ("case",)

    ordering = ("case__case_id", "character_id")

    list_select_related = ("case",)

    autocomplete_fields = ("case",)

    list_per_page = 25

    fieldsets = (
        (
            "기본 정보",
            {
                "fields": (
                    "case",
                    "character_id",
                    "name",
                ),
            },
        ),
        (
            "공개 프로필",
            {
                "fields": ("profile",),
            },
        ),
        (
            "내부 전용 정보",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
                "description": (
                    "NPC 내부 설정 정보입니다. "
                    "플레이어에게 공개하지 마세요."
                ),
            },
        ),
    )


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    """사건별 증거와 관련 NPC 및 증거 점수를 관리합니다."""

    list_display = (
        "evidence_id",
        "name",
        "case",
        "holder",
        "score",
    )

    list_display_links = ("evidence_id", "name")

    search_fields = (
        "evidence_id",
        "name",
        "case__case_id",
        "case__title",
        "holder__character_id",
        "holder__name",
    )

    list_filter = ("case",)

    ordering = ("case__case_id", "evidence_id")

    list_select_related = ("case", "holder")

    autocomplete_fields = ("case", "holder")

    list_per_page = 25

    fieldsets = (
        (
            "증거 기본 정보",
            {
                "fields": (
                    "case",
                    "evidence_id",
                    "name",
                    "score",
                ),
            },
        ),
        (
            "관련 인물",
            {
                "fields": ("holder",),
                "description": (
                    "관련 NPC는 증거와 동일한 사건에 "
                    "소속되어야 합니다."
                ),
            },
        ),
        (
            "내부 증거 메타데이터",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
                "description": (
                    "증거의 비공개 설정입니다. "
                    "플레이어에게 직접 노출하지 마세요."
                ),
            },
        ),
    )


@admin.register(EvidencePrerequisite)
class EvidencePrerequisiteAdmin(admin.ModelAdmin):
    """증거 간 선행 조건을 조회하고 관리합니다."""

    list_display = (
        "dependent",
        "prerequisite",
        "evidence_case",
    )

    search_fields = (
        "dependent__evidence_id",
        "dependent__name",
        "prerequisite__evidence_id",
        "prerequisite__name",
        "dependent__case__case_id",
    )

    list_filter = ("dependent__case",)

    ordering = (
        "dependent__case__case_id",
        "dependent__evidence_id",
        "prerequisite__evidence_id",
    )

    list_select_related = (
        "dependent__case",
        "prerequisite",
    )

    autocomplete_fields = (
        "dependent",
        "prerequisite",
    )

    list_per_page = 25

    fields = (
        "dependent",
        "prerequisite",
    )

    @admin.display(description="소속 사건")
    def evidence_case(self, obj):
        """후행 증거가 속한 사건을 표시합니다."""
        return obj.dependent.case.case_id


@admin.register(StoryEvent)
class StoryEventAdmin(admin.ModelAdmin):
    """챕터별 스토리 이벤트와 발동 조건을 관리합니다."""

    list_display = (
        "event_key",
        "trigger_type",
        "chapter",
        "case_id_display",
    )

    list_display_links = ("event_key",)

    search_fields = (
        "event_key",
        "chapter__code",
        "chapter__title",
        "chapter__case__case_id",
    )

    list_filter = (
        "trigger_type",
        "chapter__case",
    )

    ordering = (
        "chapter__case__case_id",
        "chapter__order",
        "event_key",
    )

    list_select_related = ("chapter__case",)

    autocomplete_fields = ("chapter",)

    list_per_page = 25

    fieldsets = (
        (
            "이벤트 기본 정보",
            {
                "fields": (
                    "chapter",
                    "event_key",
                    "trigger_type",
                ),
            },
        ),
        (
            "이벤트 발동 조건",
            {
                "fields": ("conditions",),
                "description": (
                    "이벤트 발동에 필요한 조건을 "
                    "JSON 객체 형태로 입력합니다."
                ),
            },
        ),
        (
            "스토리 출력 콘텐츠",
            {
                "fields": ("payload",),
                "description": (
                    "이벤트가 발생했을 때 출력할 "
                    "스토리 데이터를 입력합니다."
                ),
            },
        ),
    )

    @admin.display(description="소속 사건")
    def case_id_display(self, obj):
        """이벤트가 속한 사건 ID를 반환합니다."""
        return obj.chapter.case.case_id


@admin.register(ContentRelease)
class ContentReleaseAdmin(admin.ModelAdmin):
    """게시된 콘텐츠 버전을 읽기 전용으로 조회합니다."""

    list_display = (
        "case",
        "version",
        "published_at",
        "checksum",
    )

    list_display_links = ("version",)

    search_fields = (
        "case__case_id",
        "case__title",
        "version",
        "checksum",
    )

    list_filter = ("case",)

    ordering = ("-published_at", "-pk")

    list_select_related = ("case",)

    list_per_page = 25

    readonly_fields = (
        "case",
        "version",
        "manifest",
        "checksum",
        "published_at",
    )

    fieldsets = (
        (
            "게시 정보",
            {
                "fields": (
                    "case",
                    "version",
                    "published_at",
                    "checksum",
                ),
            },
        ),
        (
            "콘텐츠 스냅샷",
            {
                "fields": ("manifest",),
                "classes": ("collapse",),
                "description": (
                    "비공개 사건 정보가 포함될 수 있습니다. "
                    "게시된 스냅샷은 수정할 수 없습니다."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        """Admin을 통한 신규 게시 기록 생성을 금지합니다."""
        return False

    def has_change_permission(self, request, obj=None):
        """게시된 콘텐츠의 수정을 금지합니다."""
        return False

    def has_delete_permission(self, request, obj=None):
        """게시된 콘텐츠의 삭제를 금지합니다."""
        return False


@admin.register(Scene)
class SceneAdmin(admin.ModelAdmin):
    """스토리 장면 관리."""

    list_display = (
        "scene_id", "title", "case", "chapter", "visibility"
    )
    search_fields = (
        "scene_id", "title", "case__case_id", "chapter__code"
    )
    list_filter = ("case", "visibility")
    ordering = ("case__case_id", "chapter__order", "scene_id")
    list_select_related = ("case", "chapter")
    autocomplete_fields = ("case", "chapter")


@admin.register(NPCCard)
class NPCCardAdmin(admin.ModelAdmin):
    """NPC 지식 및 잡담 카드 관리."""

    list_display = ("card_id", "character", "card_type")
    search_fields = (
        "card_id",
        "content",
        "character__character_id",
        "character__name",
    )
    list_filter = ("card_type", "character__case")
    ordering = ("character__character_id", "card_id")
    list_select_related = ("character",)
    autocomplete_fields = ("character",)

    fieldsets = (
        ("기본 정보", {
            "fields": ("character", "card_id", "card_type"),
        }),
        ("카드 내용", {
            "fields": ("content",),
        }),
        ("공개 조건 및 내부 정보", {
            "fields": ("disclosure_policy", "metadata"),
            "classes": ("collapse",),
        }),
    )


@admin.register(NPCDialogueTrigger)
class NPCDialogueTriggerAdmin(admin.ModelAdmin):
    """NPC 대화 트리거 관리."""

    list_display = (
        "trigger_id",
        "character",
        "stage",
        "trigger_type",
        "output_mode",
        "is_active",
    )
    search_fields = (
        "trigger_id",
        "response_text",
        "character__name",
    )
    list_filter = (
        "stage",
        "trigger_type",
        "output_mode",
        "is_active",
    )
    ordering = ("character__character_id", "stage", "output_order")
    list_select_related = ("character",)
    autocomplete_fields = ("character",)

    fieldsets = (
        ("트리거 기본 정보", {
            "fields": (
                "character",
                "trigger_id",
                "stage",
                "trigger_type",
            ),
        }),
        ("대사 설정", {
            "fields": (
                "output_mode",
                "response_text",
                "condition_key",
                "output_order",
            ),
        }),
        ("활성화 및 내부 조건", {
            "fields": ("is_active", "metadata"),
        }),
    )


@admin.register(EvidenceLink)
class EvidenceLinkAdmin(admin.ModelAdmin):
    """증거 간 추론 관계 관리."""

    list_display = (
        "from_evidence",
        "to_evidence",
        "relationship",
        "needs_canon_approval",
        "is_active",
    )
    search_fields = (
        "from_evidence__evidence_id",
        "to_evidence__evidence_id",
        "relationship",
        "resulting_inference",
    )
    list_filter = ("needs_canon_approval", "is_active")
    list_select_related = ("from_evidence", "to_evidence")
    autocomplete_fields = ("from_evidence", "to_evidence")

    fieldsets = (
        ("증거 연결", {
            "fields": (
                "from_evidence",
                "to_evidence",
                "relationship",
                "resulting_inference",
            ),
        }),
        ("정본 승인 및 활성화", {
            "fields": (
                "needs_canon_approval",
                "is_active",
            ),
        }),
        ("추가 정보", {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
    )


@admin.register(CharacterRelationship)
class CharacterRelationshipAdmin(admin.ModelAdmin):
    """NPC와 NPC·증거·외부 인물 간 관계 관리."""

    list_display = (
        "source_character",
        "target_type",
        "target_id",
        "public_from_stage",
        "is_active",
    )
    search_fields = (
        "source_character__character_id",
        "source_character__name",
        "target_id",
        "relationship",
    )
    list_filter = (
        "target_type",
        "public_from_stage",
        "is_active",
    )
    list_select_related = ("source_character",)
    autocomplete_fields = ("source_character",)


@admin.register(Objective)
class ObjectiveAdmin(admin.ModelAdmin):
    """플레이어 목표 및 힌트 관리."""

    list_display = (
        "objective_id",
        "chapter",
        "is_active",
    )
    search_fields = (
        "objective_id",
        "player_goal",
        "chapter__code",
    )
    list_filter = ("chapter__case", "is_active")
    ordering = ("chapter__order", "objective_id")
    list_select_related = ("chapter",)
    autocomplete_fields = ("chapter",)

    fieldsets = (
        ("목표 정보", {
            "fields": (
                "chapter",
                "objective_id",
                "player_goal",
            ),
        }),
        ("힌트 및 완료 조건", {
            "fields": ("hints", "completion_rule"),
        }),
        ("활성화 및 추가 정보", {
            "fields": ("is_active", "metadata"),
        }),
    )
