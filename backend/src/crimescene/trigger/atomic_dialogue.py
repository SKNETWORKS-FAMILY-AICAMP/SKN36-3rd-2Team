"""CASE-001: NPC 대화와 GameState를 하나의 SQLite 트랜잭션으로 저장한다."""

import json
from dataclasses import replace
from pathlib import Path

from crimescene.chat.npc_chat_runtime import NPCChatTurn
from crimescene.chat.npc_rag_service import NPCRAGResources
from crimescene.chat.npc_session import (
    MAX_MESSAGE_LENGTH,
    MAX_REPLY_LENGTH,
    NPCExchange,
    NPCSessionStore,
)
from crimescene.chat.npc_session_repository import SQLiteNPCSessionRepository
from crimescene.chat.npc_social_dialogue import is_approved_social_reply
from crimescene.retriever.npc_output_guard import NPCGroundedReply
from crimescene.retriever.npc_response_gate import FALLBACK_REPLY
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.game_state import GameState
from crimescene.trigger.case001_dialogue import (
    Case001DialogueResult,
    run_case001_npc_dialogue,
)
from crimescene.trigger.npc_trigger import NPCTriggerRule


class SQLiteCase001Repository(SQLiteNPCSessionRepository):
    """NPC 대화와 게임 진행 상태를 같은 SQLite 파일에서 관리한다."""

    def commit_state(
        self,
        *,
        expected_state: GameState,
        updated_state: GameState,
    ) -> GameState:
        """일반 게임 상태 변경을 revision 검사 후 원자적으로 저장합니다."""

        if not isinstance(expected_state, GameState):
            raise TypeError("expected_state는 GameState여야 합니다.")

        if not isinstance(updated_state, GameState):
            raise TypeError("updated_state는 GameState여야 합니다.")

        if (
            expected_state.case_id != "CASE-001"
            or updated_state.case_id != expected_state.case_id
            or updated_state.session_id != expected_state.session_id
        ):
            raise ValueError("사건 또는 세션 정보가 일치하지 않습니다.")

        if updated_state.revision != expected_state.revision + 1:
            raise ValueError("revision은 정확히 1 증가해야 합니다.")

        # model_copy(update=...)로 생성된 객체도 저장 전에 다시 검증합니다.
        updated_state = GameState.model_validate(
            updated_state.model_dump(mode="python")
        )

        self._validate_session_id(expected_state.session_id)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")

            row = db.execute(
                """
                SELECT revision, state_json
                FROM game_states
                WHERE session_id = ?
                """,
                (expected_state.session_id,),
            ).fetchone()

            selection = db.execute(
                """
                SELECT active_character_id, revision
                FROM npc_sessions
                WHERE session_id = ?
                """,
                (expected_state.session_id,),
            ).fetchone()

            # 저장된 상태와 요청의 기준 상태가 정확히 일치해야 합니다.
            if (
                row is None
                or row["revision"] != expected_state.revision
                or GameState.model_validate_json(row["state_json"]) != expected_state
            ):
                raise ValueError("오래되었거나 변경된 GameState입니다.")

            if (
                selection is None
                or selection["revision"] != expected_state.revision
                or selection["active_character_id"]
                not in updated_state.unlocked_characters
            ):
                raise ValueError("NPC 세션 상태가 일치하지 않습니다.")

            # GameState와 NPC 세션 revision을 하나의 트랜잭션으로 갱신합니다.
            db.execute(
                """
                UPDATE game_states
                SET revision = ?, state_json = ?
                WHERE session_id = ?
                """,
                (
                    updated_state.revision,
                    updated_state.model_dump_json(),
                    updated_state.session_id,
                ),
            )

            db.execute(
                """
                UPDATE npc_sessions
                SET revision = ?
                WHERE session_id = ?
                """,
                (
                    updated_state.revision,
                    updated_state.session_id,
                ),
            )

        return updated_state

    def __init__(
        self,
        db_path: Path,
        *,
        max_exchanges_per_npc: int = 50,
    ) -> None:
        super().__init__(
            db_path,
            max_exchanges_per_npc=max_exchanges_per_npc,
        )

        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS game_states (
                    session_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK (revision >= 0),
                    state_json TEXT NOT NULL,
                    FOREIGN KEY (session_id)
                        REFERENCES npc_sessions(session_id)
                        ON DELETE CASCADE
                )
                """
            )

    def register_state(self, state: GameState) -> None:
        """NPC 선택 완료 후 초기 GameState를 등록한다. 재등록은 멱등 처리한다."""

        if not isinstance(state, GameState):
            raise TypeError("GameState가 필요합니다.")

        self._validate_session_id(state.session_id)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")

            selection = db.execute(
                """
                SELECT revision
                FROM npc_sessions
                WHERE session_id = ?
                """,
                (state.session_id,),
            ).fetchone()

            if selection is None or selection["revision"] != state.revision:
                raise ValueError("NPC 세션과 GameState revision이 일치하지 않습니다.")

            row = db.execute(
                """
                SELECT state_json
                FROM game_states
                WHERE session_id = ?
                """,
                (state.session_id,),
            ).fetchone()

            if row is not None:
                if GameState.model_validate_json(row["state_json"]) != state:
                    raise ValueError("이미 다른 GameState가 등록됐습니다.")
                return

            db.execute(
                """
                INSERT INTO game_states (
                    session_id,
                    revision,
                    state_json
                )
                VALUES (?, ?, ?)
                """,
                (
                    state.session_id,
                    state.revision,
                    state.model_dump_json(),
                ),
            )

    def load_state(self, session_id: str) -> GameState:
        """DB의 서버 관리 GameState를 읽는다."""

        self._validate_session_id(session_id)

        with self._connect() as db:
            row = db.execute(
                """
                SELECT revision, state_json
                FROM game_states
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            raise ValueError("등록되지 않은 게임 상태입니다.")

        state = GameState.model_validate_json(row["state_json"])

        if state.session_id != session_id or state.revision != row["revision"]:
            raise ValueError("게임 상태 저장 데이터가 손상됐습니다.")

        return state

    def commit_turn(
        self,
        *,
        expected_state: GameState,
        updated_state: GameState,
        turn: NPCChatTurn,
    ) -> GameState:
        """낙관적 버전 검사 후 GameState와 검증된 대화를 함께 커밋한다."""

        if not isinstance(expected_state, GameState):
            raise TypeError("expected_state는 GameState여야 합니다.")

        if not isinstance(updated_state, GameState):
            raise TypeError("updated_state는 GameState여야 합니다.")

        if not isinstance(turn, NPCChatTurn):
            raise TypeError("NPCChatTurn이 필요합니다.")

        if (
            expected_state.case_id != "CASE-001"
            or updated_state.case_id != expected_state.case_id
            or updated_state.session_id != expected_state.session_id
            or updated_state.revision < expected_state.revision
        ):
            raise ValueError("게임 상태의 사건·세션·revision이 잘못됐습니다.")

        self._validate_session_id(expected_state.session_id)
        self._validate_character(turn.character_id)

        reply = turn.reply
        exchange = turn.exchange

        if not isinstance(reply, NPCGroundedReply):
            raise TypeError("NPCGroundedReply가 필요합니다.")

        if not isinstance(exchange, NPCExchange):
            raise TypeError("NPCExchange가 필요합니다.")

        if (
            exchange.npc_message != reply.text.strip()
            or exchange.source_ids != reply.source_ids
            or not (
                expected_state.revision
                <= exchange.state_revision
                <= updated_state.revision
            )
        ):
            raise ValueError("NPC 응답과 대화 기록이 일치하지 않습니다.")

        if (
            not isinstance(exchange.user_message, str)
            or not 1 <= len(exchange.user_message.strip()) <= MAX_MESSAGE_LENGTH
            or not 1 <= len(exchange.npc_message) <= MAX_REPLY_LENGTH
        ):
            raise ValueError("대화 길이가 올바르지 않습니다.")

        if not isinstance(exchange.source_ids, tuple):
            raise TypeError("대화 출처 형식이 올바르지 않습니다.")

        if any(
            not isinstance(source_id, str) or not source_id.strip()
            for source_id in exchange.source_ids
        ):
            raise TypeError("대화 출처 형식이 올바르지 않습니다.")

        if len(set(exchange.source_ids)) != len(exchange.source_ids):
            raise ValueError("중복된 출처 ID입니다.")

        if reply.grounded and not reply.source_ids:
            raise ValueError("검증된 응답에는 출처가 필요합니다.")

        if not reply.grounded:
            is_safe_social = is_approved_social_reply(
                turn.character_id,
                exchange.user_message,
                reply.text,
            )

            if reply.source_ids or (
                reply.text != FALLBACK_REPLY and not is_safe_social
            ):
                raise ValueError("검증되지 않은 NPC 응답은 저장할 수 없습니다.")

        # 일반 대화도 revision을 증가시켜 경쟁 요청을 차단한다.
        committed_state = updated_state.model_copy(
            update={
                "revision": max(
                    updated_state.revision,
                    expected_state.revision + 1,
                )
            }
        )

        # GameState, NPC 기록, 세션 revision은 모두 하나의 트랜잭션이다.
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")

            row = db.execute(
                """
                SELECT revision, state_json
                FROM game_states
                WHERE session_id = ?
                """,
                (expected_state.session_id,),
            ).fetchone()

            selection = db.execute(
                """
                SELECT active_character_id, revision
                FROM npc_sessions
                WHERE session_id = ?
                """,
                (expected_state.session_id,),
            ).fetchone()

            # 최신 상태가 아니면 쓰기를 중단한다.
            if (
                row is None
                or row["revision"] != expected_state.revision
                or GameState.model_validate_json(row["state_json"]) != expected_state
            ):
                raise ValueError("오래되었거나 변조된 GameState입니다.")

            if (
                selection is None
                or selection["active_character_id"] != turn.character_id
                or selection["revision"] != expected_state.revision
            ):
                raise ValueError("NPC 선택 상태 또는 revision이 변경됐습니다.")

            # 1. 게임 상태 저장
            db.execute(
                """
                UPDATE game_states
                SET revision = ?, state_json = ?
                WHERE session_id = ?
                """,
                (
                    committed_state.revision,
                    committed_state.model_dump_json(),
                    expected_state.session_id,
                ),
            )

            # 2. 검증된 NPC 대화 저장
            db.execute(
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
                    expected_state.session_id,
                    turn.character_id,
                    exchange.user_message,
                    exchange.npc_message,
                    json.dumps(
                        exchange.source_ids,
                        ensure_ascii=False,
                    ),
                    exchange.state_revision,
                ),
            )

            # 3. NPC별 대화 기록 개수 제한
            db.execute(
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
                    expected_state.session_id,
                    turn.character_id,
                    expected_state.session_id,
                    turn.character_id,
                    self._limit,
                ),
            )

            # 4. NPC 세션 revision 동기화
            db.execute(
                """
                UPDATE npc_sessions
                SET revision = ?
                WHERE session_id = ?
                """,
                (
                    committed_state.revision,
                    expected_state.session_id,
                ),
            )

        return committed_state


class _StagedSessionRepository:
    """NPCSessionStore 검증을 재사용하되 실제 DB 쓰기는 지연한다."""

    def __init__(
        self,
        source: SQLiteCase001Repository,
    ) -> None:
        self._source = source
        self.pending: NPCExchange | None = None

    def save_selection(
        self,
        session_id: str,
        character_id: str,
        revision: int,
    ) -> None:
        raise RuntimeError("대화 처리 중 NPC 선택 변경은 허용하지 않습니다.")

    def load_selection(
        self,
        session_id: str,
    ) -> tuple[str, int] | None:
        return self._source.load_selection(session_id)

    def append_exchange(
        self,
        session_id: str,
        character_id: str,
        exchange: NPCExchange,
    ) -> None:
        if self.pending is not None:
            raise RuntimeError("하나의 트랜잭션에는 대화 한 건만 허용합니다.")

        selection = self.load_selection(session_id)

        if selection is None or selection[0] != character_id:
            raise PermissionError("현재 선택된 NPC가 아닙니다.")

        self.pending = exchange

    def load_history(
        self,
        session_id: str,
        character_id: str,
    ) -> tuple[NPCExchange, ...]:
        return self._source.load_history(
            session_id,
            character_id,
        )

    def delete_session(
        self,
        session_id: str,
    ) -> None:
        raise RuntimeError("대화 처리 중 세션 삭제는 허용하지 않습니다.")


def run_case001_npc_dialogue_atomic(
    question: str,
    *,
    session_id: str,
    repository: SQLiteCase001Repository,
    resources: NPCRAGResources,
    policies: dict[str, AccessPolicy],
    trigger_rules: tuple[NPCTriggerRule, ...],
    presented_evidence_id: str | None = None,
) -> Case001DialogueResult:
    """DB에서 신뢰 상태를 읽고 NPC 대화와 GameState를 원자적으로 저장한다."""

    if not isinstance(repository, SQLiteCase001Repository):
        raise TypeError("SQLiteCase001Repository가 필요합니다.")

    # 서버 DB에 저장된 최신 상태만 사용한다.
    state = repository.load_state(session_id)

    # 기존 #23 대화 검증은 유지하면서 DB 쓰기만 지연한다.
    staged = _StagedSessionRepository(repository)

    store = NPCSessionStore(repository=staged)

    result = run_case001_npc_dialogue(
        question,
        state=state,
        session_store=store,
        resources=resources,
        policies=policies,
        trigger_rules=trigger_rules,
        presented_evidence_id=presented_evidence_id,
    )

    if staged.pending is None or staged.pending != result.turn.exchange:
        raise RuntimeError("검증된 NPC 대화가 임시 저장되지 않았습니다.")

    committed = repository.commit_turn(
        expected_state=state,
        updated_state=result.state,
        turn=result.turn,
    )

    return replace(
        result,
        state=committed,
    )
