
"""Issue #120 - Django 내부 NPC 카드 조회 API 보안 테스트."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.content.models import Case, Character, NPCCard


TEST_TOKEN = "issue120-npc-test-token-" + "A" * 48


@override_settings(CONTENT_SERVICE_TOKEN=TEST_TOKEN)
class InternalApprovedNPCCardsAPITests(APITestCase):
    """내부 NPC 카드 API의 인증 및 공개 정책을 검증합니다."""

    @classmethod
    def setUpTestData(cls):
        cls.case = Case.objects.create(
            case_id="CASE-001",
            title="테스트 사건",
            status=Case.Status.PUBLISHED,
        )

        cls.character = Character.objects.create(
            case=cls.case,
            character_id="C01",
            name="테스트 NPC",
        )

        # 승인된 지식 카드
        cls.approved_card = NPCCard.objects.create(
            character=cls.character,
            card_id="K-C01-01",
            card_type=NPCCard.CardType.KNOWLEDGE,
            content="APPROVED_CARD_CONTENT",
            disclosure_policy={
                "status": "APPROVED",
                "allow": True,
            },
            metadata={
                "runtime_enabled": True,
                "internal_secret": "PRIVATE_METADATA",
            },
        )

        # 공개 승인이 없는 카드
        NPCCard.objects.create(
            character=cls.character,
            card_id="K-C01-02",
            card_type=NPCCard.CardType.KNOWLEDGE,
            content="UNAPPROVED_CARD_CONTENT",
            disclosure_policy={
                "status": "PENDING",
                "allow": False,
            },
            metadata={"runtime_enabled": True},
        )

        # 런타임 사용이 비활성화된 카드
        NPCCard.objects.create(
            character=cls.character,
            card_id="K-C01-S01",
            card_type=NPCCard.CardType.SMALLTALK,
            content="DISABLED_CARD_CONTENT",
            disclosure_policy={
                "status": "APPROVED",
                "allow": True,
            },
            metadata={"runtime_enabled": False},
        )

        cls.url = reverse(
            "internal-approved-npc-cards",
            kwargs={
                "case_id": "CASE-001",
                "character_id": "C01",
            },
        )

    def authenticated_get(self, url=None):
        return self.client.get(
            url or self.url,
            HTTP_X_CONTENT_SERVICE_TOKEN=TEST_TOKEN,
        )

    def test_only_approved_cards_returned(self):
        """승인된 카드만 반환하고 내부 필드는 제거합니다."""

        response = self.authenticated_get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "character_id": "C01",
                "cards": [
                    {
                        "card_id": "K-C01-01",
                        "card_type": "KNOWLEDGE",
                        "content": "APPROVED_CARD_CONTENT",
                    }
                ],
            },
        )

        body = response.content.decode("utf-8")

        for secret in (
            "UNAPPROVED_CARD_CONTENT",
            "DISABLED_CARD_CONTENT",
            "PRIVATE_METADATA",
            "disclosure_policy",
        ):
            self.assertNotIn(secret, body)

    def test_missing_token_returns_403(self):
        """서비스 토큰 없는 요청은 차단합니다."""

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_invalid_token_returns_403(self):
        """잘못된 서비스 토큰은 차단합니다."""

        response = self.client.get(
            self.url,
            HTTP_X_CONTENT_SERVICE_TOKEN="invalid-token",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(CONTENT_SERVICE_TOKEN="")
    def test_unconfigured_token_fails_closed(self):
        """서버의 인증 토큰이 미설정이면 접근을 거부합니다."""

        response = self.authenticated_get()
        self.assertEqual(response.status_code, 403)

    def test_admin_session_cannot_bypass_token(self):
        """관리자 로그인만으로 내부 API에 접근할 수 없습니다."""

        admin = get_user_model().objects.create_user(
            username="npc_api_admin",
            password="TestPassword123!",
            is_staff=True,
        )

        self.client.force_login(admin)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_draft_case_returns_404(self):
        """DRAFT 사건의 NPC 카드는 공개하지 않습니다."""

        self.case.status = Case.Status.DRAFT
        self.case.save(update_fields=["status"])

        response = self.authenticated_get()
        self.assertEqual(response.status_code, 404)

    def test_unknown_case_returns_404(self):
        """존재하지 않는 사건의 카드 조회를 차단합니다."""

        url = reverse(
            "internal-approved-npc-cards",
            kwargs={
                "case_id": "CASE-999",
                "character_id": "C01",
            },
        )

        response = self.authenticated_get(url)
        self.assertEqual(response.status_code, 404)

    def test_unknown_character_returns_404(self):
        """존재하지 않는 NPC의 카드 조회를 차단합니다."""

        url = reverse(
            "internal-approved-npc-cards",
            kwargs={
                "case_id": "CASE-001",
                "character_id": "C10",
            },
        )

        response = self.authenticated_get(url)
        self.assertEqual(response.status_code, 404)

    def test_no_approved_cards_returns_empty_list(self):
        """승인된 카드가 없으면 빈 목록을 반환합니다."""

        self.approved_card.metadata = {
            "runtime_enabled": False,
        }
        self.approved_card.save(update_fields=["metadata"])

        response = self.authenticated_get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cards"], [])

    def test_post_returns_405(self):
        """조회 전용 API에서 데이터 변경을 금지합니다."""

        response = self.client.post(
            self.url,
            {"content": "UNAUTHORIZED_CHANGE"},
            format="json",
            HTTP_X_CONTENT_SERVICE_TOKEN=TEST_TOKEN,
        )

        self.assertEqual(response.status_code, 405)
