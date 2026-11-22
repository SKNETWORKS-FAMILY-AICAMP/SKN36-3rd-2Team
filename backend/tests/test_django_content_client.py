"""Django 콘텐츠 API HTTP 클라이언트 테스트."""

import httpx
import pytest

from crimescene.api.django_content_client import (
    ContentServiceError,
    DjangoContentClient,
)

TEST_TOKEN = "test-service-token-" + "A" * 48

VALID_RESPONSE = {
    "case": {
        "case_id": "CASE-001",
        "title": "테스트 사건",
        "status": "DRAFT",
    },
    "chapters": [
        {
            "code": "CH00",
            "order": 0,
            "title": "프롤로그",
        },
        {
            "code": "CH01",
            "order": 1,
            "title": "첫 번째 챕터",
        },
    ],
}


def create_client(handler):
    """테스트용 HTTP 클라이언트를 생성합니다."""
    return DjangoContentClient(
        base_url="http://127.0.0.1:8001",
        token=TEST_TOKEN,
        timeout_seconds=3.0,
        transport=httpx.MockTransport(handler),
    )


def test_successful_case_overview():
    """정상 응답을 파싱하고 서비스 토큰을 전달합니다."""

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == ("/api/content/internal/cases/CASE-001/overview/")
        assert request.headers["X-Content-Service-Token"] == TEST_TOKEN

        return httpx.Response(
            200,
            json=VALID_RESPONSE,
        )

    with create_client(handler) as client:
        result = client.get_case_overview("CASE-001")

    assert result.case.case_id == "CASE-001"
    assert len(result.chapters) == 2
    assert result.chapters[0].code == "CH00"


@pytest.mark.parametrize("status_code", [403, 500])
def test_http_error_is_handled(status_code):
    """인증 실패 및 서버 오류를 안전하게 처리합니다."""

    def handler(request):
        return httpx.Response(
            status_code,
            json={"detail": "PRIVATE_INTERNAL_ERROR"},
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError) as exc,
    ):
        client.get_case_overview("CASE-001")

    assert f"HTTP {status_code}" in str(exc.value)
    assert "PRIVATE_INTERNAL_ERROR" not in str(exc.value)
    assert TEST_TOKEN not in str(exc.value)


def test_timeout_is_handled():
    """Django 응답 지연 시 전용 예외를 발생시킵니다."""

    def handler(request):
        raise httpx.ReadTimeout("timeout")

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match="응답 시간이 초과",
        ),
    ):
        client.get_case_overview("CASE-001")


def test_connection_failure_is_handled():
    """Django 연결 실패를 전용 예외로 변환합니다."""

    def handler(request):
        raise httpx.ConnectError("connection refused")

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match="연결할 수 없습니다",
        ),
    ):
        client.get_case_overview("CASE-001")


def test_invalid_json_is_rejected():
    """잘못된 JSON을 수용하지 않습니다."""

    def handler(request):
        return httpx.Response(
            200,
            content=b"{invalid-json",
        )

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match="응답 형식",
        ),
    ):
        client.get_case_overview("CASE-001")


def test_oversized_response_is_rejected():
    """64KB를 초과하는 응답은 거부합니다."""

    def handler(request):
        return httpx.Response(
            200,
            content=b"x" * 65_537,
        )

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match="응답 크기",
        ),
    ):
        client.get_case_overview("CASE-001")


def test_invalid_case_id_is_rejected():
    """잘못된 사건 ID는 HTTP 요청 전에 차단합니다."""

    def handler(request):
        pytest.fail("HTTP request must not be sent")

    with create_client(handler) as client, pytest.raises(ValueError):
        client.get_case_overview("../admin")


def test_mismatched_case_id_is_rejected():
    """응답의 사건 ID가 요청과 다르면 차단합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                **VALID_RESPONSE,
                "case": {
                    **VALID_RESPONSE["case"],
                    "case_id": "CASE-999",
                },
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match="사건 ID가 일치하지 않습니다",
        ),
    ):
        client.get_case_overview("CASE-001")


def test_redirect_is_not_followed():
    """내부 서비스 토큰이 다른 URL로 전달되지 않도록 합니다."""

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            302,
            headers={
                "Location": "https://example.com/redirect",
            },
        )

    with create_client(handler) as client, pytest.raises(ContentServiceError):
        client.get_case_overview("CASE-001")

    assert len(requests) == 1


def test_evidence_requirements_success():
    """승인된 선행 증거 조건을 정상적으로 조회합니다."""

    def handler(request):
        assert request.url.path == (
            "/api/content/internal/cases/CASE-001/evidence/E03/requirements/"
        )
        return httpx.Response(
            200,
            json={
                "evidence_id": "E03",
                "prerequisites": ["E01", "E02"],
                "player_unlock_verification_required": True,
            },
        )

    with create_client(handler) as client:
        result = client.get_evidence_requirements("CASE-001", "E03")

    assert result.prerequisites == ["E01", "E02"]


@pytest.mark.parametrize(
    "prerequisites",
    [
        ["E03"],  # 자기참조
        ["E01", "E01"],  # 중복
        ["E99"],  # 잘못된 증거 ID
    ],
)
def test_invalid_evidence_requirements_rejected(prerequisites):
    """잘못된 선행 조건을 모두 차단합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "evidence_id": "E03",
                "prerequisites": prerequisites,
                "player_unlock_verification_required": True,
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError),
    ):
        client.get_evidence_requirements("CASE-001", "E03")


def test_evidence_requirements_not_approved():
    """Django에서 승인하지 않은 증거는 조회할 수 없습니다."""

    def handler(request):
        return httpx.Response(404)

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError, match="HTTP 404"),
    ):
        client.get_evidence_requirements("CASE-001", "E03")


def test_evidence_id_mismatch_rejected():
    """다른 증거의 선행 조건이 전달되면 차단합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "evidence_id": "E04",
                "prerequisites": ["E01"],
                "player_unlock_verification_required": True,
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError, match="일치하지 않습니다"),
    ):
        client.get_evidence_requirements("CASE-001", "E03")


def test_player_scene_success():
    """승인된 장면을 정상적으로 조회합니다."""

    def handler(request):
        assert request.url.path == (
            "/api/content/internal/cases/CASE-001/scenes/SC-0001/"
        )
        return httpx.Response(
            200,
            json={
                "scene_id": "SC-0001",
                "chapter": "CH00",
                "title": "프롤로그",
                "scene_text": "사건이 시작됩니다.",
            },
        )

    with create_client(handler) as client:
        scene = client.get_player_scene("CASE-001", "SC-0001")

    assert scene.scene_id == "SC-0001"
    assert scene.chapter == "CH00"
    assert scene.scene_text == "사건이 시작됩니다."


@pytest.mark.parametrize("status_code", [404, 500])
def test_player_scene_http_error(status_code):
    """미승인 장면 및 Django 서버 오류를 처리합니다."""

    def handler(request):
        return httpx.Response(
            status_code,
            json={"detail": "PRIVATE_SCENE"},
        )

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match=f"HTTP {status_code}",
        ),
    ):
        client.get_player_scene("CASE-001", "SC-0001")


def test_player_scene_id_mismatch():
    """다른 장면이 응답으로 전달되면 차단합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "scene_id": "SC-0002",
                "chapter": "CH00",
                "title": "다른 장면",
                "scene_text": "공개하면 안 되는 본문",
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match="일치하지 않습니다",
        ),
    ):
        client.get_player_scene("CASE-001", "SC-0001")


def test_player_scene_rejects_extra_fields():
    """계약에 없는 내부 메타데이터를 거부합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "scene_id": "SC-0001",
                "chapter": "CH00",
                "title": "프롤로그",
                "scene_text": "사건이 시작됩니다.",
                "case_truth": "PRIVATE",
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError, match="응답 형식"),
    ):
        client.get_player_scene("CASE-001", "SC-0001")


@pytest.mark.parametrize(
    "scene_id",
    ["../admin", "SC-99999"],
)
def test_player_scene_invalid_id(scene_id):
    """잘못된 장면 ID는 요청 전에 차단합니다."""

    def handler(request):
        pytest.fail("HTTP 요청이 발생하면 안 됩니다.")

    with create_client(handler) as client, pytest.raises(ValueError):
        client.get_player_scene("CASE-001", scene_id)


def test_player_scene_timeout():
    """장면 조회 타임아웃을 안전하게 처리합니다."""

    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError, match="시간이 초과"),
    ):
        client.get_player_scene("CASE-001", "SC-0001")


def test_approved_npc_cards_success():
    """승인된 NPC 카드 응답을 검증합니다."""

    def handler(request):
        assert request.headers["X-Content-Service-Token"] == TEST_TOKEN
        assert request.url.path == (
            "/api/content/internal/cases/CASE-001/characters/C01/cards/"
        )

        return httpx.Response(
            200,
            json={
                "character_id": "C01",
                "cards": [
                    {
                        "card_id": "K-C01-01",
                        "card_type": "KNOWLEDGE",
                        "content": "승인된 지식 카드",
                    }
                ],
            },
        )

    with create_client(handler) as client:
        result = client.get_approved_npc_cards("CASE-001", "C01")

    assert result.character_id == "C01"
    assert result.cards[0].card_id == "K-C01-01"


def test_approved_npc_cards_empty():
    """승인된 카드가 없어도 정상적인 빈 목록을 허용합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={"character_id": "C01", "cards": []},
        )

    with create_client(handler) as client:
        result = client.get_approved_npc_cards("CASE-001", "C01")

    assert result.cards == []


@pytest.mark.parametrize("status_code", [403, 404, 500])
def test_approved_npc_cards_http_error(status_code):
    """인증 실패, 미게시 사건 및 서버 장애를 처리합니다."""

    def handler(request):
        return httpx.Response(
            status_code,
            json={"detail": "PRIVATE_ERROR"},
        )

    with (
        create_client(handler) as client,
        pytest.raises(
            ContentServiceError,
            match=f"HTTP {status_code}",
        ) as exc,
    ):
        client.get_approved_npc_cards("CASE-001", "C01")

    assert "PRIVATE_ERROR" not in str(exc.value)


def test_approved_npc_cards_rejects_private_fields():
    """내부 메타데이터가 포함된 응답은 거부합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "character_id": "C01",
                "cards": [
                    {
                        "card_id": "K-C01-01",
                        "card_type": "KNOWLEDGE",
                        "content": "테스트",
                        "metadata": {"secret": "PRIVATE"},
                    }
                ],
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError),
    ):
        client.get_approved_npc_cards("CASE-001", "C01")


def test_approved_npc_cards_rejects_other_character():
    """다른 NPC의 카드를 포함하면 차단합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "character_id": "C01",
                "cards": [
                    {
                        "card_id": "K-C02-01",
                        "card_type": "KNOWLEDGE",
                        "content": "다른 NPC의 정보",
                    }
                ],
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError),
    ):
        client.get_approved_npc_cards("CASE-001", "C01")


def test_approved_npc_cards_rejects_duplicates():
    """중복된 카드 ID를 차단합니다."""

    card = {
        "card_id": "K-C01-01",
        "card_type": "KNOWLEDGE",
        "content": "테스트 카드",
    }

    def handler(request):
        return httpx.Response(
            200,
            json={
                "character_id": "C01",
                "cards": [card, card],
            },
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError),
    ):
        client.get_approved_npc_cards("CASE-001", "C01")


def test_approved_npc_cards_character_mismatch():
    """응답 NPC가 요청한 NPC와 다르면 차단합니다."""

    def handler(request):
        return httpx.Response(
            200,
            json={"character_id": "C02", "cards": []},
        )

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError, match="일치하지 않습니다"),
    ):
        client.get_approved_npc_cards("CASE-001", "C01")


def test_approved_npc_cards_timeout():
    """조회 타임아웃을 전용 오류로 처리합니다."""

    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with (
        create_client(handler) as client,
        pytest.raises(ContentServiceError, match="시간이 초과"),
    ):
        client.get_approved_npc_cards("CASE-001", "C01")
