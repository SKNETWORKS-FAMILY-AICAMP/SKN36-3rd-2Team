from pathlib import Path

from pydantic import TypeAdapter

from crimescene.scenario.models import CaseMetadata, TimelineEvent

_timeline_adapter = TypeAdapter(list[TimelineEvent])


def load_case_metadata(file_path: Path) -> CaseMetadata:
    """JSON 파일에서 사건 기본 정보를 불러온다."""

    content = file_path.read_text(encoding="utf-8")

    return CaseMetadata.model_validate_json(content)


def load_engine_timeline(file_path: Path) -> list[TimelineEvent]:
    """관리자 전용 사건 타임라인을 불러온다.

    이 함수가 반환하는 데이터는 게임 엔진 전용이며,
    NPC 프롬프트 및 RAG 검색 인덱스에 전달하면 안 된다.
    """

    content = file_path.read_text(encoding="utf-8")

    events = _timeline_adapter.validate_json(content)

    # 사건 ID 중복 검사
    event_ids = [event.event_id for event in events]

    if len(event_ids) != len(set(event_ids)):
        raise ValueError("사건 타임라인에 중복된 event_id가 존재합니다.")

    return events
