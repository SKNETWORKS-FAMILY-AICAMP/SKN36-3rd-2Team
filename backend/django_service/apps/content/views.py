
"""Django 콘텐츠 관리 API."""

from django.shortcuts import get_object_or_404

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import HasContentServiceToken

from .access_policy import is_runtime_approved
from .models import Evidence, NPCCard, Objective, Scene

from .models import Case, Chapter
from .serializers import (
    CaseSummarySerializer,
    ChapterSummarySerializer,
)

from django.http import Http404
from .access_policy import can_serve_player_scene


class CaseOverviewView(APIView):
    """관리자 전용 사건 및 챕터 개요 조회."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str):
        case = get_object_or_404(
            Case,
            case_id=case_id,
        )

        chapters = (
            Chapter.objects
            .filter(case=case)
            .order_by("order", "code")
        )

        return Response({
            "case": CaseSummarySerializer(case).data,
            "chapters": ChapterSummarySerializer(
                chapters,
                many=True,
            ).data,
        })


class InternalCaseOverviewView(APIView):
    """인증된 백엔드 서비스 전용 사건 개요 API."""

    # Django 세션 인증을 허용하지 않습니다.
    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str):
        case = get_object_or_404(
            Case,
            case_id=case_id,
        )

        chapters = (
            Chapter.objects
            .filter(case=case)
            .order_by("order", "code")
        )

        return Response({
            "case": CaseSummarySerializer(case).data,
            "chapters": ChapterSummarySerializer(
                chapters,
                many=True,
            ).data,
        })


class InternalContentReadinessView(APIView):
    """사건별 콘텐츠 런타임 승인 현황을 조회합니다."""

    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str):
        case = get_object_or_404(
            Case,
            case_id=case_id,
        )

        datasets = {
            "scenes": Scene.objects.filter(case=case),
            "evidence": Evidence.objects.filter(case=case),
            "npc_cards": NPCCard.objects.filter(
                character__case=case
            ),
            "objectives": Objective.objects.filter(
                chapter__case=case
            ),
        }

        result = {}

        for resource, queryset in datasets.items():
            total = queryset.count()

            # 승인 상태는 DB 메타데이터를 기준으로 서버에서 판단합니다.
            approved = sum(
                1
                for content in queryset.iterator(chunk_size=200)
                if is_runtime_approved(content)
            )

            result[resource] = {
                "total": total,
                "approved": approved,
                "blocked": total - approved,
            }

        return Response({
            "case_id": case.case_id,
            "resources": result,
        })


class InternalPlayerSceneView(APIView):
    """FastAPI 전용 플레이어 공개 가능 Scene 상세 조회."""

    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str, scene_id: str):
        scene = get_object_or_404(
            Scene.objects.select_related("case", "chapter"),
            case__case_id=case_id,
            scene_id=scene_id,
        )

        # 권한이 없는 콘텐츠도 존재하지 않는 것처럼 응답합니다.
        if not can_serve_player_scene(scene):
            raise Http404

        return Response({
            "scene_id": scene.scene_id,
            "chapter": scene.chapter.code,
            "title": scene.title,
            "scene_text": scene.scene_text,
        })


class InternalEvidenceRequirementsView(APIView):
    """FastAPI 전용 증거 해금 요구사항 조회 API."""

    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str, evidence_id: str):
        evidence = get_object_or_404(
            Evidence.objects.select_related("case"),
            case__case_id=case_id,
            evidence_id=evidence_id,
        )

        # 게시되지 않은 사건의 증거는 조회할 수 없습니다.
        if evidence.case.status != Case.Status.PUBLISHED:
            raise Http404

        # 미승인 증거는 존재 여부조차 노출하지 않습니다.
        if not is_runtime_approved(evidence):
            raise Http404

        # 선행 증거를 모두 가져와 승인 상태를 검증합니다.
        edges = list(
            evidence.prerequisite_edges
            .select_related("prerequisite")
            .order_by("prerequisite__evidence_id")
        )

        # 미승인 선행 증거나 다른 사건의 증거가 하나라도
        # 연결되어 있다면 전체 요청을 차단합니다.
        for edge in edges:
            prerequisite = edge.prerequisite

            if (
                prerequisite.case_id != evidence.case_id
                or not is_runtime_approved(prerequisite)
            ):
                raise Http404

        prerequisite_ids = [
            edge.prerequisite.evidence_id
            for edge in edges
        ]


        return Response({
            "evidence_id": evidence.evidence_id,
            "prerequisites": prerequisite_ids,
            "player_unlock_verification_required": True,
        })
