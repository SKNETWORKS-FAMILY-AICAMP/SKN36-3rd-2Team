
"""Django 콘텐츠 관리 API."""
import re

from .models import StoryEvent
from django.shortcuts import get_object_or_404

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import HasContentServiceToken

from .access_policy import is_runtime_approved
from .models import Character, Evidence, NPCCard, Objective, Scene

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

class InternalApprovedNPCCardsView(APIView):
    """인증된 게임 엔진 전용 NPC 승인 카드 조회."""

    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str, character_id: str):
        character = get_object_or_404(
            Character.objects.select_related("case"),
            case__case_id=case_id,
            character_id=character_id,
        )

        # 게시되지 않은 사건은 NPC 카드 조회를 차단합니다.
        if character.case.status != Case.Status.PUBLISHED:
            raise Http404

        cards = [
            {
                "card_id": card.card_id,
                "card_type": card.card_type,
                "content": card.content,
            }
            for card in NPCCard.objects.filter(
                character=character
            ).order_by("card_id").iterator(chunk_size=200)
            if is_runtime_approved(card)
        ]

        # 메타데이터와 공개 정책 원문은 반환하지 않습니다.
        return Response({
            "character_id": character.character_id,
            "cards": cards,
        })


class InternalApprovedStoryEventView(APIView):
    """FastAPI 전용 승인된 증거 획득 스토리 이벤트 조회."""

    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id: str, event_key: str):
        event = get_object_or_404(
            StoryEvent.objects.select_related("chapter__case"),
            chapter__case__case_id=case_id,
            event_key=event_key,
        )

        if event.chapter.case.status != Case.Status.PUBLISHED:
            raise Http404

        if not is_runtime_approved(event):
            raise Http404

        # 아직 계약이 없는 이벤트 유형은 런타임에서 차단합니다.
        if event.trigger_type != StoryEvent.TriggerType.EVIDENCE_COLLECTED:
            raise Http404

        conditions = event.conditions
        payload = event.payload

        # 지원하는 조건 외의 JSON 필드는 해석하지 않고 차단합니다.
        if set(conditions) != {"requiredEvidenceIds"}:
            raise Http404

        evidence_ids = conditions["requiredEvidenceIds"]

        if (
            not isinstance(evidence_ids, list)
            or not 1 <= len(evidence_ids) <= 30
            or any(
                not isinstance(item, str)
                or re.fullmatch(
                    r"E(?:0[1-9]|[12][0-9]|30)",
                    item,
                ) is None
                for item in evidence_ids
            )
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise Http404

        # 출력 콘텐츠는 허용된 필드만 반환합니다.
        if set(payload) - {"title", "text"}:
            raise Http404

        title = payload.get("title")
        text = payload.get("text", "")

        if (
            not isinstance(title, str)
            or not 1 <= len(title.strip()) <= 120
            or not isinstance(text, str)
            or len(text) > 5000
        ):
            raise Http404

        return Response({
            "event_key": event.event_key,
            "chapter": event.chapter.code,
            "trigger_type": event.trigger_type,
            "required_evidence_ids": evidence_ids,
            "title": title,
            "text": text,
        })
