
"""콘텐츠 API URL 설정."""

from django.urls import path

from .views import CaseOverviewView, InternalCaseOverviewView

# 기존 views import 목록에 추가
from .views import InternalContentReadinessView, InternalPlayerSceneView, InternalEvidenceRequirementsView
from .views import InternalApprovedNPCCardsView
from .views import InternalApprovedStoryEventView

urlpatterns = [
    path(
        "cases/<str:case_id>/overview/",
        CaseOverviewView.as_view(),
        name="case-overview",
    ),

    path(
        "internal/cases/<str:case_id>/overview/",
        InternalCaseOverviewView.as_view(),
        name="internal-case-overview",
    ),


    path(
        "internal/cases/<str:case_id>/readiness/",
        InternalContentReadinessView.as_view(),
        name="internal-content-readiness",
    ),

    path(
        "internal/cases/<str:case_id>/scenes/<str:scene_id>/",
        InternalPlayerSceneView.as_view(),
        name="internal-player-scene",
    ),

    path(
        "internal/cases/<str:case_id>/evidence/<str:evidence_id>/requirements/",
        InternalEvidenceRequirementsView.as_view(),
        name="internal-evidence-requirements",
    ),

    path(
        "internal/cases/<str:case_id>/characters/<str:character_id>/cards/",
        InternalApprovedNPCCardsView.as_view(),
        name="internal-approved-npc-cards",
    ),

    path(
        "internal/cases/<str:case_id>/events/<str:event_key>/",
        InternalApprovedStoryEventView.as_view(),
        name="internal-approved-story-event",
    ),

]
