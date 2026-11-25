"""Issue #155 - 인증된 MCP Server의 읽기 전용 Client 실행 계층.

Python 3.13 / MCP SDK 2.3 / Pydantic 2
"""

import asyncio
import math
from collections.abc import Collection
from typing import Annotated, Any

from mcp import Client
from mcp.server import MCPServer
from mcp.shared.exceptions import MCPError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

from crimescene.mcp.evidence_tools import EvidenceSearchPayload
from crimescene.mcp.npc_tools import NPCKnowledgePayload
from crimescene.mcp.server import (
    GameContextPayload,
    InvestigationProgressPayload,
)


class MCPToolError(RuntimeError):
    """MCP Tool 실행 계층의 기본 예외."""


class MCPToolPermissionError(MCPToolError):
    """허용되지 않은 Tool 실행 요청."""


class MCPToolValidationError(MCPToolError):
    """Tool 입력 또는 응답 스키마 검증 실패."""


class MCPToolExecutionError(MCPToolError):
    """MCP 연결 또는 Tool 실행 실패."""


class MCPToolTimeoutError(MCPToolError):
    """MCP 실행 제한 시간 초과."""


class EvidenceSearchArguments(BaseModel):
    """MCP 증거 검색 입력 계약."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    query: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=200,
        ),
    ]
    limit: int = Field(default=3, ge=1, le=5)


_OUTPUT_SCHEMAS = {
    "get_game_context": TypeAdapter(GameContextPayload),
    "get_investigation_progress": TypeAdapter(
        InvestigationProgressPayload
    ),
    "get_npc_knowledge": TypeAdapter(NPCKnowledgePayload),
    "search_authorized_evidence": TypeAdapter(
        EvidenceSearchPayload
    ),
}

SUPPORTED_TOOLS = frozenset(_OUTPUT_SCHEMAS)


class MCPToolClient:
    """서버가 승인한 읽기 전용 MCP Tool만 실행합니다.

    반드시 서버 인증이 완료된 MCPServer를 전달해야 합니다.
    이 클래스는 세션 소유권 인증을 대신하지 않습니다.
    """

    def __init__(
        self,
        *,
        server: MCPServer,
        allowed_tools: Collection[str],
        timeout_seconds: float = 15.0,
    ) -> None:
        if not isinstance(server, MCPServer):
            raise TypeError(
                "서버에서 생성한 MCPServer가 필요합니다."
            )

        if (
            not isinstance(allowed_tools, Collection)
            or isinstance(allowed_tools, (str, bytes))
            or not allowed_tools
        ):
            raise ValueError(
                "서버에서 승인한 Tool 목록이 필요합니다."
            )

        if any(
            not isinstance(tool, str)
            or tool not in SUPPORTED_TOOLS
            for tool in allowed_tools
        ):
            raise MCPToolPermissionError(
                "지원하지 않는 Tool이 포함되어 있습니다."
            )

        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 120
        ):
            raise ValueError(
                "Timeout은 0초 초과 120초 이하여야 합니다."
            )

        self._server = server
        self._allowed_tools = frozenset(allowed_tools)
        self._timeout_seconds = float(timeout_seconds)

    @property
    def allowed_tools(self) -> frozenset[str]:
        """서버가 승인한 변경 불가능한 Tool 목록입니다."""

        return self._allowed_tools

    def _validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Tool별 입력 계약을 검증합니다."""

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, dict):
            raise MCPToolValidationError(
                "Tool 입력은 dictionary여야 합니다."
            )

        if tool_name == "search_authorized_evidence":
            try:
                validated = (
                    EvidenceSearchArguments.model_validate(
                        arguments
                    )
                )
            except ValidationError:
                raise MCPToolValidationError(
                    "증거 검색 입력이 올바르지 않습니다."
                ) from None

            return validated.model_dump()

        # 나머지 Tool은 사용자 입력 인자를 허용하지 않습니다.
        if arguments:
            raise MCPToolValidationError(
                "입력 인자를 허용하지 않는 Tool입니다."
            )

        return {}

    def _validate_output(
        self,
        tool_name: str,
        payload: object,
    ) -> dict[str, Any]:
        """기존 MCP Payload 계약으로 응답을 검증합니다."""

        if not isinstance(payload, dict):
            raise MCPToolValidationError(
                "유효한 구조화 응답이 없습니다."
            )

        try:
            return _OUTPUT_SCHEMAS[tool_name].validate_python(
                payload,
                strict=True,
                extra="forbid",
            )
        except ValidationError:
            raise MCPToolValidationError(
                "MCP 응답 스키마가 일치하지 않습니다."
            ) from None

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """승인된 Tool을 실제 MCP SDK를 통해 실행합니다."""

        # SDK 연결 전에 권한과 입력을 검증합니다.
        if (
            not isinstance(tool_name, str)
            or tool_name not in self._allowed_tools
        ):
            raise MCPToolPermissionError(
                "허용되지 않은 MCP Tool입니다."
            )

        validated_arguments = self._validate_arguments(
            tool_name,
            arguments,
        )

        try:
            # 연결, 호출 및 종료를 포함한 전체 실행 시간 제한.
            async with asyncio.timeout(self._timeout_seconds):
                async with Client(
                    self._server,
                    raise_exceptions=False,
                    read_timeout_seconds=self._timeout_seconds,
                    cache=None,
                ) as client:
                    result = await client.call_tool(
                        tool_name,
                        validated_arguments,
                        read_timeout_seconds=(
                            self._timeout_seconds
                        ),
                    )

            if result.is_error:
                raise MCPToolExecutionError(
                    "MCP Tool 실행에 실패했습니다."
                )

            return self._validate_output(
                tool_name,
                result.structured_content,
            )

        except TimeoutError:
            raise MCPToolTimeoutError(
                "MCP 실행 제한 시간을 초과했습니다."
            ) from None

        except MCPToolError:
            raise

        except (
            MCPError,
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            ExceptionGroup,
        ):
            # 인증 정보, 내부 경로 및 원본 Tool 오류를
            # 상위 서비스에 그대로 노출하지 않습니다.
            raise MCPToolExecutionError(
                "MCP 서비스 실행 중 오류가 발생했습니다."
            ) from None
