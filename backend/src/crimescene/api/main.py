"""FastAPI 실행 진입점."""

import os
from pathlib import Path

from crimescene.api.app import create_app
from crimescene.trigger.atomic_dialogue import SQLiteCase001Repository

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
)
