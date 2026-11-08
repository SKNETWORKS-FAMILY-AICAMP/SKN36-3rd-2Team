"""Issue #23 - SQLite 기반 NPC 대화 기록 영구 저장소.

이 모듈은 내부 데이터 저장 계층이다.
NPC 접근 권한 및 LLM 응답 검증은 기존 서비스 계층에서 수행한다.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from crimescene.chat.npc_persona import EXPECTED_CHARACTER_IDS
from crimescene.chat.npc_session import (
    MAX_MESSAGE_LENGTH,
    MAX_REPLY_LENGTH,
    NPCExchange,
)


class SQLiteNPCSessionRepository:
    """게임 세션과 NPC별 대화 기록을 SQLite에 저장한다."""

    def __init__(
        self,
        db_path: Path,
        *,
        max_exchanges_per_npc: int = 50,
    ) -> None:
        if not isinstance(db_path, Path):
            raise TypeError("DB 경로는 Path 객체여야 합니다.")

        if isinstance(max_exchanges_per_npc, bool) or not isinstance(
            max_exchanges_per_npc, int
        ):
            raise TypeError("대화 기록 제한은 정수여야 합니다.")

        if max_exchanges_per_npc < 1:
            raise ValueError("대화 기록 제한은 1 이상이어야 합니다.")

        self._path = db_path
        self._limit = max_exchanges_per_npc

        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """연결을 생성하고 트랜잭션을 관리한다."""

        connection = sqlite3.connect(
            self._path,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        """필요한 테이블을 생성한다."""

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS npc_sessions (
                    session_id TEXT PRIMARY KEY,
                    active_character_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 0)
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS npc_exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    npc_message TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    state_revision INTEGER NOT NULL,
                    FOREIGN KEY (session_id)
                        REFERENCES npc_sessions(session_id)
                        ON DELETE CASCADE
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_npc_exchanges_history
                ON npc_exchanges(session_id, character_id, id)
                """
            )

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not isinstance(session_id, str):
            raise TypeError("세션 ID는 문자열이어야 합니다.")

        if not session_id.strip() or len(session_id) > 128:
            raise ValueError("유효하지 않은 세션 ID입니다.")

    @staticmethod
    def _validate_character(character_id: str) -> None:
        if not isinstance(character_id, str):
            raise TypeError("NPC ID는 문자열이어야 합니다.")

        if character_id not in EXPECTED_CHARACTER_IDS:
            raise ValueError("유효하지 않은 NPC ID입니다.")

    @staticmethod
    def _validate_revision(revision: int) -> None:
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise TypeError("revision은 정수여야 합니다.")

        if revision < 0:
            raise ValueError("revision은 0 이상이어야 합니다.")

    def save_selection(
        self,
        session_id: str,
        character_id: str,
        revision: int,
    ) -> None:
        """현재 NPC 선택 상태를 영구 저장한다."""

        self._validate_session_id(session_id)
        self._validate_character(character_id)
        self._validate_revision(revision)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            current = connection.execute(
                """
                SELECT revision
                FROM npc_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            if current is not None and revision < current["revision"]:
                raise ValueError("오래된 GameState revision입니다.")

            connection.execute(
                """
                INSERT INTO npc_sessions (
                    session_id,
                    active_character_id,
                    revision
                )
                VALUES (?, ?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET
                    active_character_id = excluded.active_character_id,
                    revision = excluded.revision
                """,
                (session_id, character_id, revision),
            )

    def load_selection(
        self,
        session_id: str,
    ) -> tuple[str, int] | None:
        """저장된 NPC 선택 상태와 revision을 조회한다."""

        self._validate_session_id(session_id)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT active_character_id, revision
                FROM npc_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        character_id = row["active_character_id"]
        revision = row["revision"]

        self._validate_character(character_id)
        self._validate_revision(revision)

        return character_id, revision

    def append_exchange(
        self,
        session_id: str,
        character_id: str,
        exchange: NPCExchange,
    ) -> None:
        """기존 서비스에서 검증한 대화 기록을 추가한다."""

        self._validate_session_id(session_id)
        self._validate_character(character_id)

        if not isinstance(exchange, NPCExchange):
            raise TypeError("NPCExchange 객체가 필요합니다.")

        self._validate_revision(exchange.state_revision)

        if (
            not exchange.user_message.strip()
            or len(exchange.user_message) > MAX_MESSAGE_LENGTH
        ):
            raise ValueError("플레이어 메시지가 올바르지 않습니다.")

        if (
            not exchange.npc_message.strip()
            or len(exchange.npc_message) > MAX_REPLY_LENGTH
        ):
            raise ValueError("NPC 메시지가 올바르지 않습니다.")

        if not isinstance(exchange.source_ids, tuple):
            raise TypeError("출처 목록은 튜플이어야 합니다.")

        if any(
            not isinstance(source_id, str) or not source_id.strip()
            for source_id in exchange.source_ids
        ):
            raise ValueError("출처 ID가 올바르지 않습니다.")

        if len(exchange.source_ids) != len(set(exchange.source_ids)):
            raise ValueError("중복된 출처 ID입니다.")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            current = connection.execute(
                """
                SELECT active_character_id, revision
                FROM npc_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

            if current is None:
                raise ValueError("등록되지 않은 게임 세션입니다.")

            if current["active_character_id"] != character_id:
                raise PermissionError("현재 선택된 NPC가 아닙니다.")

            if exchange.state_revision < current["revision"]:
                raise ValueError("오래된 GameState revision입니다.")

            connection.execute(
                """
                INSERT INTO npc_exchanges (
                    session_id,
                    character_id,
                    user_message,
                    npc_message,
                    source_ids_json,
                    state_revision
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    character_id,
                    exchange.user_message,
                    exchange.npc_message,
                    json.dumps(
                        exchange.source_ids,
                        ensure_ascii=False,
                    ),
                    exchange.state_revision,
                ),
            )

            # NPC별 최신 N개 기록만 유지한다.
            connection.execute(
                """
                DELETE FROM npc_exchanges
                WHERE session_id = ?
                  AND character_id = ?
                  AND id NOT IN (
                      SELECT id
                      FROM npc_exchanges
                      WHERE session_id = ?
                        AND character_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (
                    session_id,
                    character_id,
                    session_id,
                    character_id,
                    self._limit,
                ),
            )

            connection.execute(
                """
                UPDATE npc_sessions
                SET revision = ?
                WHERE session_id = ?
                """,
                (exchange.state_revision, session_id),
            )

    def load_history(
        self,
        session_id: str,
        character_id: str,
    ) -> tuple[NPCExchange, ...]:
        """해당 게임 세션과 NPC의 기록만 조회한다."""

        self._validate_session_id(session_id)
        self._validate_character(character_id)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    user_message,
                    npc_message,
                    source_ids_json,
                    state_revision
                FROM npc_exchanges
                WHERE session_id = ?
                  AND character_id = ?
                ORDER BY id ASC
                """,
                (session_id, character_id),
            ).fetchall()

        history = []

        for row in rows:
            source_ids = json.loads(row["source_ids_json"])

            if (
                not isinstance(source_ids, list)
                or any(
                    not isinstance(source_id, str) or not source_id.strip()
                    for source_id in source_ids
                )
                or len(source_ids) != len(set(source_ids))
            ):
                raise ValueError("저장된 출처 데이터가 올바르지 않습니다.")

            if not isinstance(row["user_message"], str):
                raise TypeError("저장된 플레이어 메시지가 올바르지 않습니다.")

            if not isinstance(row["npc_message"], str):
                raise TypeError("저장된 NPC 메시지가 올바르지 않습니다.")

            self._validate_revision(row["state_revision"])

            history.append(
                NPCExchange(
                    user_message=row["user_message"],
                    npc_message=row["npc_message"],
                    source_ids=tuple(source_ids),
                    state_revision=row["state_revision"],
                )
            )

        return tuple(history)

    def delete_session(self, session_id: str) -> None:
        """게임 세션과 해당 세션의 모든 대화 기록을 삭제한다."""

        self._validate_session_id(session_id)

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM npc_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            )
