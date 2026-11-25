"""Issue #165 - version-isolated retrieval."""

from crimescene.scenario.schemas.game_state import GameState

LEGACY_VERSION = "case001_v7_1"
EXPANDED_VERSION = "case001_1120"

LEGACY_COLLECTION = "case001_rag_v1"
EXPANDED_COLLECTION = "case001_rag_1120_staging"
REVISION1_COLLECTION = "case001_rag_1120_revision1"
REVISION2_COLLECTION = "case001_rag_1120_revision2"

LEGACY_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 11)
)

EXPANDED_IDS = frozenset(
    f"E{i:02d}" for i in range(1, 31)
)


def evidence_ids_for_version(version: str) -> frozenset[str]:
    if version == LEGACY_VERSION:
        return LEGACY_IDS

    if version == EXPANDED_VERSION:
        return EXPANDED_IDS

    raise ValueError("Unsupported content version")


def validate_catalog_version(version: str, rules) -> None:
    expected = evidence_ids_for_version(version)
    actual = set(rules)

    if not actual or not actual.issubset(expected):
        raise ValueError("Evidence catalog version mismatch")

    if version == EXPANDED_VERSION and actual != expected:
        raise ValueError("Expanded catalog requires 30 evidence IDs")


def retrieval_options(
    state: GameState,
    *,
    collection_name: str | None = None,
) -> dict[str, str]:
    if state.content_version == LEGACY_VERSION:
        if collection_name not in (None, LEGACY_COLLECTION):
            raise PermissionError("Legacy collection mismatch")

        return {}

    if state.content_version == EXPANDED_VERSION:
        selected = (
            EXPANDED_COLLECTION
            if collection_name is None
            else collection_name
        )

        if selected not in {
            EXPANDED_COLLECTION,
            REVISION1_COLLECTION,
            REVISION2_COLLECTION,
        }:
            raise PermissionError("Expanded collection mismatch")

        return {"collection_name": selected}

    raise ValueError("Unsupported retrieval version")
