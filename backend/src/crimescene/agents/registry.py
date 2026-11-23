
"""Issue #130 - Agent 등록 및 조회 관리."""

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from crimescene.agents.contracts import AgentExecutor, AgentType


class AgentRegistry:
    """서버에서 등록한 Agent만 조회할 수 있는 Registry."""

    def __init__(self, agents: Iterable[AgentExecutor] = ()) -> None:
        registered: dict[AgentType, AgentExecutor] = {}

        for agent in agents:
            agent_type = getattr(agent, "agent_type", None)

            if not isinstance(agent_type, AgentType):
                raise TypeError("올바른 AgentType이 필요합니다.")

            if not callable(getattr(agent, "execute", None)):
                raise TypeError("Agent 실행 메서드가 필요합니다.")

            if agent_type in registered:
                raise ValueError(
                    f"중복 등록된 Agent입니다: {agent_type}"
                )

            registered[agent_type] = agent

        # 초기화 이후 등록 목록 변경 방지
        self._agents: Mapping[AgentType, AgentExecutor] = (
            MappingProxyType(registered)
        )

    def resolve(self, agent_type: AgentType) -> AgentExecutor:
        """서버에 등록된 Agent를 조회합니다."""

        if not isinstance(agent_type, AgentType):
            raise TypeError("올바른 AgentType이 필요합니다.")

        try:
            return self._agents[agent_type]
        except KeyError:
            raise LookupError(
                f"등록되지 않은 Agent입니다: {agent_type}"
            ) from None
