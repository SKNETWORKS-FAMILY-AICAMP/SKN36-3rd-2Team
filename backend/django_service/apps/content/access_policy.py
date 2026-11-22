
"""게임 콘텐츠의 런타임 사용 승인 여부를 검증합니다.

승인 여부와 플레이어별 해금 여부는 별개입니다.
이 함수가 True여도 플레이어에게 즉시 공개할 수는 없습니다.
"""

from .models import (
    Case,
    Evidence,
    NPCCard,
    Objective,
    Scene,
    StoryEvent,
)

def is_runtime_approved(
    content: Scene | Evidence | NPCCard | Objective | StoryEvent,
) -> bool:
    """명시적 승인이 없는 모든 콘텐츠를 거부합니다."""

    metadata = getattr(content, "metadata", None)

    if not isinstance(metadata, dict):
        return False

    if metadata.get("runtime_enabled") is not True:
        return False

    if isinstance(content, Scene):
        return (
            content.metadata.get("backend_contract_approved") is True
            and content.visibility in Scene.Visibility.values
        )

    if isinstance(content, Evidence):
        return (
            metadata.get("canon_approved") is True
            and metadata.get("publication_approved") is True
        )

    if isinstance(content, NPCCard):
        policy = content.disclosure_policy

        return (
            isinstance(policy, dict)
            and policy.get("status") == "APPROVED"
            and policy.get("allow") is True
        )

    if isinstance(content, Objective):
        return (
            content.is_active is True
            and isinstance(content.completion_rule, dict)
            and bool(content.completion_rule)
            and metadata.get("completion_rule_approved") is True
        )

    if isinstance(content, StoryEvent):
        return (
            metadata.get("backend_contract_approved") is True
            and isinstance(content.conditions, dict)
            and bool(content.conditions)
            and isinstance(content.payload, dict)
            and bool(content.payload)
        )

    return False


def can_serve_player_scene(scene: Scene) -> bool:
    """플레이어에게 전달 가능한 Scene인지 검증합니다."""

    if not isinstance(scene, Scene):
        return False

    # 게시되지 않은 사건은 외부에 공개하지 않습니다.
    if scene.case.status != Case.Status.PUBLISHED:
        return False

    # 별도 해금 검증기가 없으므로 기본 공개 Scene만 허용합니다.
    if scene.visibility != Scene.Visibility.PLAYER_VISIBLE:
        return False

    # 런타임 승인 및 Backend 계약 승인도 필요합니다.
    return is_runtime_approved(scene)
