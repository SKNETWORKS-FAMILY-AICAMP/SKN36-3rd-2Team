"""Django Health API 자동화 테스트."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class HealthAPITests(APITestCase):
    """Health API의 응답 및 접근 정책을 검증합니다."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("health")

    def test_health_get_without_authentication(self):
        """로그인하지 않아도 Health API에 접근할 수 있어야 합니다."""
        response = self.client.get(
            self.url,
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_health_response_schema(self):
        """응답은 정의된 JSON 구조와 값을 가져야 합니다."""
        response = self.client.get(
            self.url,
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            response.headers["Content-Type"].startswith("application/json")
        )
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "django",
            },
        )

    def test_health_post_not_allowed(self):
        """Health API는 POST 요청을 허용하지 않아야 합니다."""
        response = self.client.post(
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
