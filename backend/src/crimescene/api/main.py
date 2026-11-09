"""FastAPI 실행 진입점."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from crimescene.api.app import create_app
from crimescene.api.chat_bootstrap import load_chat_runtime
from crimescene.scenario.loaders.case_truth_loader import load_case001_truth
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository


@asynccontextmanager
async def chat_lifespan(app: FastAPI):
    """API 서버 시작 시 RAG 클라이언트를 열고 종료 시 닫습니다."""
    enabled = os.getenv("CRIMESCENE_ENABLE_CHAT", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if not enabled:
        yield
        return

    with load_chat_runtime() as runtime:
        app.state.dialogue_resources = runtime.resources
        app.state.dialogue_policies = runtime.policies
        app.state.dialogue_triggers = runtime.triggers
        app.state.dialogue_flag_config = runtime.flag_config
        app.state.acquisition_policy_ids = runtime.acquisition_policy_ids
        app.state.acquisition_evaluator = runtime.acquisition_evaluator
        try:
            yield
        finally:
            for name in (
                "dialogue_resources",
                "dialogue_policies",
                "dialogue_triggers",
                "dialogue_flag_config",
                "acquisition_policy_ids",
                "acquisition_evaluator",
            ):
                delattr(app.state, name)


load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

repository = SQLiteCase001Repository(
    Path(
        os.getenv(
            "CRIMESCENE_DB_PATH",
            "data/game_state.sqlite3",
        )
    )
)

app = create_app(
    repository,
    session_secret=os.environ["CRIMESCENE_SESSION_SECRET"],
    secure_cookie=os.getenv(
        "CRIMESCENE_COOKIE_SECURE",
        "false",
    ).lower()
    == "true",
    lifespan=chat_lifespan,
)

# 범인 정답은 서버 로컬 파일에서만 읽습니다.
truth_path = os.getenv("CRIMESCENE_CASE_TRUTH_PATH", "").strip()

if truth_path:
    app.state.case_truth = load_case001_truth(Path(truth_path).expanduser().resolve())
