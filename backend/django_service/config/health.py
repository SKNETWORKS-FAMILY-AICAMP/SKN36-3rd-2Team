"""Django 서비스 상태 확인 API."""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """외부 의존성 없이 Django 프로세스의 응답 상태를 확인합니다."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "status": "ok",
            "service": "django",
        })
