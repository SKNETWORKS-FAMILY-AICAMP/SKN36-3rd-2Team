"""CASE-001 expanded content integration entrypoint."""

import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from crimescene.api.app import create_app
from crimescene.api.expanded_chapter_runtime import (
    configure_expanded_chapters,
)
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.api.expanded_investigation_runtime import (
    configure_published_investigations,
)
from crimescene.api.expanded_npc_acquisition_runtime import (
    configure_published_npc_acquisitions,
)
from crimescene.api.expanded_progression_runtime import (
    configure_published_progression,
)
from crimescene.api.expanded_release_runtime import (
    BASE_URL,
    load_expanded_release_resources,
)
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = BACKEND_ROOT.parent

load_dotenv(BACKEND_ROOT / ".env", override=False)

LOCAL_ROOT = PROJECT_ROOT / ".local"

RELEASE_ROOT = LOCAL_ROOT / "case001_1120_release"

SOURCE_DIR = (
    LOCAL_ROOT / "case001_1120_source/content/case001"
)

CATALOG_PATH = (
    LOCAL_ROOT / "case001_1120_runtime/catalog.draft.json"
)

DATASET_ROOT = LOCAL_ROOT / "case001_1120_rag"

CONTENT_VERSION = "case001_1120"

RELEASE_VERSION = os.getenv(
    "CRIMESCENE_EXPANDED_RELEASE_VERSION",
    "v0.11.0",
).strip()

DB_PATH = Path(
    os.getenv(
        "CRIMESCENE_EXPANDED_DB_PATH",
        str(RELEASE_ROOT / "expanded_game_state.sqlite3"),
    )
).expanduser().resolve()

TOKEN_PATH = RELEASE_ROOT / "service-token.txt"

RUNTIME_ATTRIBUTES = (
    "dialogue_resources",
    "dialogue_policies",
    "dialogue_triggers",
    "dialogue_flag_config",
    "django_content_client",
    "e30_approval_check",
    "approved_acquisition_routes",
    "e26_section_a_approved",
    "approved_investigation_actions",
    "investigation_release_version",
    "published_npc_acquisition",
    "presentation_stage_rules",
    "approved_inference_rules",
    "approved_objective_rules",
    "chapter_unlock_rules",
    "story_event_bindings",
    "story_event_conditions",
)


@asynccontextmanager
async def expanded_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Load and verify all published runtime components."""

    app.state.expanded_runtime_ready = False

    token = TOKEN_PATH.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not token:
        raise ValueError("Content service token missing")

    with (
        load_expanded_release_resources(
            catalog_path=CATALOG_PATH,
            dataset_root=DATASET_ROOT,
            token=token,
            release_version=RELEASE_VERSION,
        ) as resources,
        DjangoContentClient(
            base_url=BASE_URL,
            token=token,
        ) as django,
    ):
        try:
            if resources.content_version != CONTENT_VERSION:
                raise ValueError("Runtime version mismatch")

            app.state.dialogue_resources = resources

            app.state.dialogue_policies = (
                resources.evaluator.snapshot_policies()
            )

            # Do not mix legacy trigger or unlock rules.
            app.state.dialogue_triggers = ()
            app.state.dialogue_flag_config = None
            app.state.django_content_client = django

            manifest = configure_published_investigations(
                app=app,
                token=token,
                catalog_path=CATALOG_PATH,
                release_version=RELEASE_VERSION,
            )

            configure_published_npc_acquisitions(
                app=app,
                manifest=manifest,
                source_dir=SOURCE_DIR,
            )

            configure_published_progression(
                app=app,
                manifest=manifest,
                source_dir=SOURCE_DIR,
            )

            configure_expanded_chapters(
                app=app,
                manifest=manifest,
                release_version=RELEASE_VERSION,
            )

            review_version = os.getenv(
                "CRIMESCENE_E30_CONSENT_REVIEW_VERSION",
                "",
            ).strip()

            if review_version:
                release_checksum = "sha256:" + hashlib.sha256(
                    json.dumps(
                        manifest,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()

                def check_e30_approval(state):
                    return django.get_e30_consent_approval(
                        case_id=state.case_id,
                        release_version=RELEASE_VERSION,
                        release_checksum=release_checksum,
                        review_version=review_version,
                    )

                app.state.e30_approval_check = check_e30_approval

                print("E30 CONSENT REVIEW: CONFIGURED")

            else:
                print("E30 CONSENT REVIEW: NOT CONFIGURED")

            app.state.expanded_runtime_ready = True

            print("=" * 60)
            print("EXPANDED APPLICATION READY")
            print("CONTENT VERSION:", CONTENT_VERSION)
            print("RELEASE VERSION:", RELEASE_VERSION)
            print("DJANGO:", BASE_URL)
            print("=" * 60)

            yield

        finally:
            app.state.expanded_runtime_ready = False

            for name in RUNTIME_ATTRIBUTES:
                if hasattr(app.state, name):
                    delattr(app.state, name)


DB_PATH.parent.mkdir(parents=True, exist_ok=True)

repository = SQLiteCase001Repository(DB_PATH)

app = create_app(
    repository,
    session_secret=os.environ["CRIMESCENE_SESSION_SECRET"],
    secure_cookie=(
        os.getenv(
            "CRIMESCENE_COOKIE_SECURE", "false"
        ).lower() == "true"
    ),
    lifespan=expanded_lifespan,
)

app.state.content_version = CONTENT_VERSION
app.state.django_evidence_gate_enabled = True
app.state.expanded_runtime_ready = False
