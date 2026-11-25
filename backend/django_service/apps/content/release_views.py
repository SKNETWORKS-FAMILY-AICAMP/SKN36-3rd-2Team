"""Version-bound content release endpoint."""

import hashlib
import json

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from .access_policy import is_runtime_approved
from .models import Case, ContentRelease, Evidence
from .permissions import HasContentServiceToken


class InternalContentReleaseView(APIView):
    authentication_classes = []
    permission_classes = [HasContentServiceToken]
    http_method_names = ["get", "head", "options"]

    def get(self, request, case_id, version):
        release = get_object_or_404(
            ContentRelease.objects.select_related("case"),
            case__case_id=case_id,
            case__status=Case.Status.PUBLISHED,
            version=version,
        )

        manifest = release.manifest

        if not isinstance(manifest, dict):
            raise Http404

        digest = hashlib.sha256(
            json.dumps(
                manifest,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        if release.checksum != f"sha256:{digest}":
            raise Http404

        if (
            manifest.get("case_id") != case_id
            or manifest.get("content_version") != "case001_1120"
            or manifest.get("scope") != "LOCAL_INTEGRATION_TEST"
        ):
            raise Http404

        approved = manifest.get("approved_evidence")

        if not isinstance(approved, dict) or not approved:
            raise Http404

        sections = manifest.get("approved_e26_sections", [])

        # E26 section approval is independent of evidence approval.
        if "E26" in approved:
            if (
                sections != ["A"]
                or "E20" not in approved
                or not isinstance(approved["E26"], dict)
                or approved["E26"].get("score") != 3
                or approved["E26"].get("required_evidence") != ["E20"]
            ):
                raise Http404

        elif sections != []:
            raise Http404

        for eid, contract in approved.items():
            evidence = get_object_or_404(
                Evidence,
                case=release.case,
                evidence_id=eid,
            )

            if not isinstance(contract, dict):
                raise Http404

            if not is_runtime_approved(evidence):
                raise Http404

            if (
                evidence.score != contract.get("score")
                or evidence.metadata.get("source_sha256")
                != contract.get("source_sha256")
                or evidence.metadata.get("content_version")
                != manifest["content_version"]
            ):
                raise Http404

            prerequisites = list(
                evidence.prerequisites.order_by("evidence_id")
                .values_list("evidence_id", flat=True)
            )

            if prerequisites != sorted(
                contract.get("required_evidence", [])
            ):
                raise Http404

        return Response({
            "version": release.version,
            "checksum": release.checksum,
            "manifest": manifest,
        })


class InternalInvestigationSceneView(InternalContentReleaseView):
    """Trusted backend lookup for published investigation scenes."""

    def get(self, request, case_id, version, scene_id):
        from .models import Scene

        release_data = super().get(
            request, case_id, version
        ).data

        manifest = release_data["manifest"]

        contracts = [
            item
            for item in manifest.get(
                "approved_investigation_actions", {}
            ).values()
            if item["scene_id"] == scene_id
        ]

        if not contracts:
            raise Http404

        contract = contracts[0]

        for item in contracts:
            if (
                item["chapter"] != contract["chapter"]
                or item["source_sha256"]
                != contract["source_sha256"]
                or item["content_sha256"]
                != contract["content_sha256"]
                or item["evidence_id"]
                not in manifest["approved_evidence"]
            ):
                raise Http404

        scene = get_object_or_404(
            Scene.objects.select_related("case", "chapter"),
            case__case_id=case_id,
            scene_id=scene_id,
        )

        if (
            scene.visibility != "UNLOCKED_ONLY"
            or not is_runtime_approved(scene)
            or scene.chapter.code != contract["chapter"]
            or scene.metadata.get("content_version")
            != manifest["content_version"]
            or scene.metadata.get("source_sha256")
            != contract["source_sha256"]
            or contract["evidence_id"]
            not in manifest["approved_evidence"]
        ):
            raise Http404

        digest = hashlib.sha256(
            json.dumps(
                {
                    "title": scene.title,
                    "scene_text": scene.scene_text,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        if digest != contract["content_sha256"]:
            raise Http404

        return Response({
            "scene_id": scene.scene_id,
            "chapter": scene.chapter.code,
            "title": scene.title,
            "scene_text": scene.scene_text,
        })
