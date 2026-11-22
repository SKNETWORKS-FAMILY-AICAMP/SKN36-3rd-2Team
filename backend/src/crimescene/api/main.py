"""FastAPI 실행 진입점."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from crimescene.api.app import create_app
from crimescene.api.chat_bootstrap import load_chat_runtime
from crimescene.api.django_content_client import DjangoContentClient
from crimescene.scenario.loaders.case_truth_loader import load_case001_truth
from crimescene.settings import settings
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


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Django 콘텐츠 클라이언트와 기존 RAG 자원을 관리합니다."""

    # Django 연동이 꺼져 있어도 기존 게임 엔진은 동작합니다.
    if not settings.django_content_enabled:
        async with chat_lifespan(app):
            yield
        return

    token = settings.django_content_service_token.get_secret_value()

    # 클라이언트 생성 시 서비스 URL과 인증 설정을 검증합니다.
    with DjangoContentClient(
        base_url=settings.django_content_base_url,
        token=token,
        timeout_seconds=settings.django_content_timeout_seconds,
    ) as client:
        app.state.django_content_client = client

        try:
            # 기존 RAG Lifespan을 그대로 유지합니다.
            async with chat_lifespan(app):
                yield
        finally:
            # 종료 시 앱 참조를 제거합니다.
            del app.state.django_content_client


load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

backend_root = Path(__file__).resolve().parents[3]

db_path = Path(os.getenv("CRIMESCENE_DB_PATH", "data/game_state.sqlite3")).expanduser()

if not db_path.is_absolute():
    db_path = backend_root / db_path

repository = SQLiteCase001Repository(db_path.resolve())

app = create_app(
    repository,
    session_secret=os.environ["CRIMESCENE_SESSION_SECRET"],
    secure_cookie=os.getenv(
        "CRIMESCENE_COOKIE_SECURE",
        "false",
    ).lower()
    == "true",
    lifespan=app_lifespan,
)
# Django 증거 해금 정책 적용 여부
app.state.django_evidence_gate_enabled = settings.django_evidence_gate_enabled
# 범인 정답은 서버 로컬 파일에서만 읽습니다.
truth_path = os.getenv("CRIMESCENE_CASE_TRUTH_PATH", "").strip()

if truth_path:
    app.state.case_truth = load_case001_truth(Path(truth_path).expanduser().resolve())
