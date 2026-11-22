"""FastAPI에서 사용하는 Django 내부 콘텐츠 API 클라이언트."""

import re
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ContentServiceError(RuntimeError):
    """Django 콘텐츠 서비스 호출 또는 응답 검증 실패."""


class ContentServiceNotFoundError(ContentServiceError):
    """존재하지 않거나 공개 승인이 없는 콘텐츠."""


class CaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str
    title: str
    status: str


class ChapterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str
    order: int
    title: str


class CaseOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case: CaseSummary
    chapters: list[ChapterSummary]


EVIDENCE_ID_PATTERN = r"^E(?:0[1-9]|[12][0-9]|30)$"


class EvidenceRequirements(BaseModel):
    """Django에서 승인한 증거 선행 조건."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str
    prerequisites: list[str]
    player_unlock_verification_required: Literal[True]

    @model_validator(mode="after")
    def validate_requirements(self):
        """증거 ID, 중복 및 자기참조를 차단합니다."""

        all_ids = [self.evidence_id, *self.prerequisites]

        if any(re.fullmatch(EVIDENCE_ID_PATTERN, item) is None for item in all_ids):
            raise ValueError("유효하지 않은 증거 ID입니다.")

        if self.evidence_id in self.prerequisites:
            raise ValueError("증거 자기참조는 허용되지 않습니다.")

        if len(self.prerequisites) != len(set(self.prerequisites)):
            raise ValueError("중복된 선행 증거가 존재합니다.")

        return self


class PlayerScene(BaseModel):
    """Django가 플레이어 공개를 승인한 스토리 장면."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scene_id: str
    chapter: str
    title: str
    scene_text: str

    @model_validator(mode="after")
    def validate_scene(self):
        if not re.fullmatch(r"SC-\d{4}", self.scene_id):
            raise ValueError("올바르지 않은 장면 ID입니다.")

        if not re.fullmatch(r"CH0[0-4]", self.chapter):
            raise ValueError("올바르지 않은 챕터 코드입니다.")

        if not self.title.strip() or not self.scene_text.strip():
            raise ValueError("장면 제목 또는 본문이 비어 있습니다.")

        return self


class ApprovedNPCCard(BaseModel):
    """Django에서 런타임 사용을 승인한 서버 내부 NPC 카드."""

    model_config = ConfigDict(extra="forbid", strict=True)

    card_id: str
    card_type: Literal["KNOWLEDGE", "SMALLTALK"]
    content: str

    @model_validator(mode="after")
    def validate_card(self):
        if not re.fullmatch(
            r"K-C(?:0[1-9]|10)-(?:\d{2}|S\d{2})",
            self.card_id,
        ):
            raise ValueError("올바르지 않은 NPC 카드 ID입니다.")

        suffix = self.card_id.rsplit("-", 1)[-1]

        if (self.card_type == "SMALLTALK") != suffix.startswith("S"):
            raise ValueError("NPC 카드 유형과 ID가 일치하지 않습니다.")

        if not self.content.strip():
            raise ValueError("NPC 카드 내용이 비어 있습니다.")

        return self


class ApprovedNPCCards(BaseModel):
    """NPC별 승인된 카드 목록. 플레이어 공개 권한과는 별개입니다."""

    model_config = ConfigDict(extra="forbid", strict=True)

    character_id: str
    cards: list[ApprovedNPCCard]

    @model_validator(mode="after")
    def validate_cards(self):
        if not re.fullmatch(r"C(?:0[1-9]|10)", self.character_id):
            raise ValueError("올바르지 않은 NPC ID입니다.")

        card_ids = [card.card_id for card in self.cards]

        if len(card_ids) != len(set(card_ids)):
            raise ValueError("중복된 NPC 카드가 존재합니다.")

        if any(
            not card_id.startswith(f"K-{self.character_id}-") for card_id in card_ids
        ):
            raise ValueError("다른 NPC의 카드가 포함되어 있습니다.")

        return self


class ApprovedStoryEvent(BaseModel):
    """Django에서 승인한 증거 획득 스토리 이벤트."""

    model_config = ConfigDict(extra="forbid", strict=True)

    event_key: str
    chapter: Literal["CH00", "CH01", "CH02", "CH03", "CH04"]
    trigger_type: Literal["EVIDENCE_COLLECTED"]
    required_evidence_ids: list[str] = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(max_length=5000)

    @model_validator(mode="after")
    def validate_event(self):
        if not re.fullmatch(
            r"EVT-CH0[0-4]-\d{3}",
            self.event_key,
        ):
            raise ValueError("올바르지 않은 이벤트 ID입니다.")

        if not self.event_key.startswith(f"EVT-{self.chapter}-"):
            raise ValueError("이벤트와 챕터가 일치하지 않습니다.")

        evidence_ids = self.required_evidence_ids

        if any(
            not re.fullmatch(r"E(?:0[1-9]|[12][0-9]|30)", item) for item in evidence_ids
        ):
            raise ValueError("올바르지 않은 선행 증거입니다.")

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("중복된 선행 증거입니다.")

        if not self.title.strip():
            raise ValueError("이벤트 제목이 비어 있습니다.")

        return self


class DjangoContentClient:
    """서버 전용 토큰으로 Django API를 조회합니다."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 3.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("올바르지 않은 Django 서비스 URL입니다.")

        # 평문 HTTP는 로컬 개발 환경에서만 허용합니다.
        if parsed.scheme == "http" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("원격 Django 서비스에는 HTTPS가 필요합니다.")

        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("Django 서비스 인증 토큰이 설정되지 않았습니다.")

        if not 0 < timeout_seconds <= 30:
            raise ValueError("Django API 타임아웃 설정이 잘못되었습니다.")

        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={
                "X-Content-Service-Token": token,
                "Accept": "application/json",
            },
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def get_approved_story_event(
        self,
        case_id: str,
        event_key: str,
    ) -> ApprovedStoryEvent:
        """게시 승인된 스토리 이벤트 정의를 조회합니다."""

        if not isinstance(case_id, str) or not re.fullmatch(r"CASE-\d{3}", case_id):
            raise ValueError("올바르지 않은 사건 ID입니다.")

        if not isinstance(event_key, str) or not re.fullmatch(
            r"EVT-CH0[0-4]-\d{3}", event_key
        ):
            raise ValueError("올바르지 않은 이벤트 ID입니다.")

        path = f"api/content/internal/cases/{case_id}/events/{event_key}/"

        try:
            response = self._client.get(path)
        except httpx.TimeoutException as exc:
            raise ContentServiceError(
                "스토리 이벤트 조회 시간이 초과되었습니다."
            ) from exc
        except httpx.RequestError as exc:
            raise ContentServiceError(
                "Django 콘텐츠 서비스에 연결할 수 없습니다."
            ) from exc

        if response.status_code == 404:
            raise ContentServiceNotFoundError("스토리 이벤트를 찾을 수 없습니다.")

        if response.status_code != 200:
            raise ContentServiceError(
                f"스토리 이벤트 조회 실패: HTTP {response.status_code}"
            )

        if len(response.content) > 65_536:
            raise ContentServiceError("스토리 이벤트 응답 크기를 초과했습니다.")

        try:
            event = ApprovedStoryEvent.model_validate_json(response.content)
        except (ValidationError, ValueError) as exc:
            raise ContentServiceError(
                "스토리 이벤트 응답 형식이 올바르지 않습니다."
            ) from exc

        if event.event_key != event_key:
            raise ContentServiceError("요청과 응답의 이벤트 ID가 일치하지 않습니다.")

        return event

    def get_case_overview(self, case_id: str) -> CaseOverview:
        """사건·챕터 개요를 조회하고 응답 스키마를 검증합니다."""

        if not isinstance(case_id, str) or not re.fullmatch(r"CASE-\d{3}", case_id):
            raise ValueError("올바르지 않은 사건 ID입니다.")

        try:
            response = self._client.get(
                f"api/content/internal/cases/{case_id}/overview/"
            )
        except httpx.TimeoutException as exc:
            raise ContentServiceError(
                "Django 콘텐츠 서비스 응답 시간이 초과되었습니다."
            ) from exc
        except httpx.RequestError as exc:
            raise ContentServiceError(
                "Django 콘텐츠 서비스에 연결할 수 없습니다."
            ) from exc

        if response.status_code == 404:
            raise ContentServiceNotFoundError("스토리 장면 조회 실패: HTTP 404")
        if response.status_code != 200:
            # 응답 본문이나 토큰은 오류 메시지에 포함하지 않습니다.
            raise ContentServiceError(
                f"Django 콘텐츠 조회 실패: HTTP {response.status_code}"
            )

        if len(response.content) > 65_536:
            raise ContentServiceError("콘텐츠 API 응답 크기를 초과했습니다.")

        try:
            overview = CaseOverview.model_validate_json(response.content)
        except ValidationError as exc:
            raise ContentServiceError(
                "Django 콘텐츠 API 응답 형식이 올바르지 않습니다."
            ) from exc

        if overview.case.case_id != case_id:
            raise ContentServiceError("Django 콘텐츠 API 사건 ID가 일치하지 않습니다.")

        return overview

    def get_evidence_requirements(
        self,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceRequirements:
        """Django에서 승인한 증거 선행 조건을 조회합니다."""

        if not isinstance(case_id, str) or not re.fullmatch(r"CASE-\d{3}", case_id):
            raise ValueError("올바르지 않은 사건 ID입니다.")

        if not isinstance(evidence_id, str) or not re.fullmatch(
            EVIDENCE_ID_PATTERN, evidence_id
        ):
            raise ValueError("올바르지 않은 증거 ID입니다.")

        path = (
            f"api/content/internal/cases/{case_id}/evidence/{evidence_id}/requirements/"
        )

        try:
            response = self._client.get(path)
        except httpx.TimeoutException as exc:
            raise ContentServiceError(
                "증거 해금 조건 조회 시간이 초과되었습니다."
            ) from exc
        except httpx.RequestError as exc:
            raise ContentServiceError(
                "Django 콘텐츠 서비스에 연결할 수 없습니다."
            ) from exc

        if response.status_code != 200:
            raise ContentServiceError(
                f"증거 해금 조건 조회 실패: HTTP {response.status_code}"
            )

        if len(response.content) > 65_536:
            raise ContentServiceError("증거 해금 조건 응답 크기를 초과했습니다.")

        try:
            result = EvidenceRequirements.model_validate_json(response.content)
        except ValidationError as exc:
            raise ContentServiceError(
                "증거 해금 조건 응답 형식이 올바르지 않습니다."
            ) from exc

        if result.evidence_id != evidence_id:
            raise ContentServiceError("요청한 증거와 응답 증거가 일치하지 않습니다.")

        return result

    def get_player_scene(
        self,
        case_id: str,
        scene_id: str,
    ) -> PlayerScene:
        """승인된 플레이어용 Scene을 Django에서 조회합니다."""

        if not isinstance(case_id, str) or not re.fullmatch(r"CASE-\d{3}", case_id):
            raise ValueError("올바르지 않은 사건 ID입니다.")

        if not isinstance(scene_id, str) or not re.fullmatch(r"SC-\d{4}", scene_id):
            raise ValueError("올바르지 않은 장면 ID입니다.")

        path = f"api/content/internal/cases/{case_id}/scenes/{scene_id}/"

        try:
            response = self._client.get(path)
        except httpx.TimeoutException as exc:
            raise ContentServiceError(
                "스토리 장면 조회 시간이 초과되었습니다."
            ) from exc
        except httpx.RequestError as exc:
            raise ContentServiceError(
                "Django 콘텐츠 서비스에 연결할 수 없습니다."
            ) from exc

        if response.status_code == 404:
            raise ContentServiceNotFoundError("??? ?? ?? ??: HTTP 404")

        if response.status_code != 200:
            # 미승인 장면(404)도 응답 본문을 노출하지 않습니다.
            raise ContentServiceError(
                f"스토리 장면 조회 실패: HTTP {response.status_code}"
            )

        if len(response.content) > 65_536:
            raise ContentServiceError("스토리 장면 응답 크기를 초과했습니다.")

        try:
            scene = PlayerScene.model_validate_json(response.content)
        except ValidationError as exc:
            raise ContentServiceError(
                "스토리 장면 응답 형식이 올바르지 않습니다."
            ) from exc

        if scene.scene_id != scene_id:
            raise ContentServiceError("요청한 장면과 응답 장면이 일치하지 않습니다.")

        return scene

    def get_approved_npc_cards(
        self,
        case_id: str,
        character_id: str,
    ) -> ApprovedNPCCards:
        """Django의 런타임 승인 NPC 카드만 조회합니다."""

        if not isinstance(case_id, str) or not re.fullmatch(r"CASE-\d{3}", case_id):
            raise ValueError("올바르지 않은 사건 ID입니다.")

        if not isinstance(character_id, str) or not re.fullmatch(
            r"C(?:0[1-9]|10)", character_id
        ):
            raise ValueError("올바르지 않은 NPC ID입니다.")

        path = f"api/content/internal/cases/{case_id}/characters/{character_id}/cards/"

        try:
            response = self._client.get(path)
        except httpx.TimeoutException as exc:
            raise ContentServiceError("NPC 카드 조회 시간이 초과되었습니다.") from exc
        except httpx.RequestError as exc:
            raise ContentServiceError(
                "Django 콘텐츠 서비스에 연결할 수 없습니다."
            ) from exc

        if response.status_code != 200:
            raise ContentServiceError(
                f"NPC 카드 조회 실패: HTTP {response.status_code}"
            )

        if len(response.content) > 65_536:
            raise ContentServiceError("NPC 카드 응답 크기를 초과했습니다.")

        try:
            result = ApprovedNPCCards.model_validate_json(response.content)
        except ValidationError as exc:
            raise ContentServiceError(
                "NPC 카드 응답 형식이 올바르지 않습니다."
            ) from exc

        if result.character_id != character_id:
            raise ContentServiceError("요청한 NPC와 응답 NPC가 일치하지 않습니다.")

        return result

    def close(self) -> None:
        """HTTP 연결 자원을 해제합니다."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
