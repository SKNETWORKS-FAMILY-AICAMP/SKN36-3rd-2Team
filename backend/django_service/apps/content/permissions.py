
"""Django 콘텐츠 API 접근 권한 검증."""

import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasContentServiceToken(BasePermission):
    """FastAPI 등 신뢰된 백엔드만 접근하도록 제한합니다."""

    message = "Access denied."

    def has_permission(self, request, view) -> bool:
        expected = getattr(
            settings,
            "CONTENT_SERVICE_TOKEN",
            "",
        )

        provided = request.headers.get(
            "X-Content-Service-Token",
            "",
        )

        # 설정이 없거나 비정상적인 토큰은 기본 거부합니다.
        if (
            not isinstance(expected, str)
            or not isinstance(provided, str)
            or len(expected) < 32
            or not provided
            or len(provided) > 512
        ):
            return False

        # 문자열 비교 시간 차이를 이용한 공격을 방지합니다.
        return hmac.compare_digest(
            expected.encode("utf-8"),
            provided.encode("utf-8"),
        )
