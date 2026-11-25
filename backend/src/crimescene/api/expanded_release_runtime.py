"""Version-bound expanded evidence release runtime."""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace

import httpx

from crimescene.api.django_content_client import DjangoContentClient
from crimescene.api.expanded_chat_bootstrap import (
    load_expanded_staging_resources,
)
from crimescene.api.expanded_npc_release import (
    activate_published_npc_cards,
)
from crimescene.api.expanded_acquisition_runtime import (
    validate_e26_release_contract,
)
from crimescene.api.expanded_rag_binding import (
    resolve_rag_binding,
    validate_e26_rag_publication,
)
from crimescene.ingest.expanded_dataset import load_verified_dataset
from crimescene.retriever.expanded_graph_publication import (
    validate_e26_holder_approval,
)
from crimescene.scenario.policy_evaluator import PolicyEvaluator
from crimescene.scenario.schemas.access_policy import AccessPolicy
from crimescene.scenario.schemas.document import PlayerDocument

VERSION = "case001_1120"
DRAFT_FLAG = "INTERNAL_DRAFT_NOT_PUBLISHED"
BASE_URL = "http://127.0.0.1:18004"
PROTECTED_IDS = frozenset({"E26", "E30"})


def load_release_manifest(token, release_version):
    with httpx.Client(
        base_url=BASE_URL,
        headers={"X-Content-Service-Token": token},
        timeout=10,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = client.get(
            f"/api/content/internal/cases/CASE-001/releases/{release_version}/"
        )

        response.raise_for_status()

        if len(response.content) > 65536:
            raise ValueError("Release response too large")

        data = response.json()

    manifest = data["manifest"]

    digest = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if (
        data["version"] != release_version
        or data["checksum"] != f"sha256:{digest}"
        or manifest["case_id"] != "CASE-001"
        or manifest["content_version"] != VERSION
        or manifest["scope"] != "LOCAL_INTEGRATION_TEST"
    ):
        raise ValueError("Invalid release manifest")

    return manifest


@contextmanager
def load_expanded_release_resources(
    *,
    catalog_path,
    dataset_root,
    token,
    release_version,
):
    manifest = load_release_manifest(
        token,
        release_version,
    )

    dataset_root, collection_name = resolve_rag_binding(
        manifest,
        dataset_root,
    )

    approved = manifest["approved_evidence"]

    if not isinstance(approved, dict) or not approved:
        raise ValueError("Approved evidence required")

    protected = set(approved) & PROTECTED_IDS

    if protected - {"E26"}:
        raise PermissionError("Protected evidence requires review")

    if protected and not validate_e26_release_contract(manifest):
        raise PermissionError("E26-A release approval required")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))

    if not set(approved).issubset(catalog["evidence"]):
        raise ValueError("Unknown published evidence")

    with (
        load_expanded_staging_resources(
            catalog_path=catalog_path,
            dataset_root=dataset_root,
            collection_name=collection_name,
        ) as resources,
        DjangoContentClient(
            base_url=BASE_URL,
            token=token,
        ) as django,
    ):
        _, documents, cards, policies = load_verified_dataset(
            dataset_root,
            expected_collection=collection_name,
        )

        validate_e26_rag_publication(
            manifest,
            documents,
            cards,
            policies,
        )

        updated = []
        published_ids = set()

        for document in documents:
            ids = document.source_evidence_ids

            if len(ids) != 1 or ids[0] not in approved:
                updated.append(document)
                continue

            eid = ids[0]
            contract = approved[eid]

            if eid in {
                "E01",
                "E02",
                "E03",
                "E04",
                "E05",
                "E06",
                "E08",
                "E09",
                "E10",
            } and (
                document.doc_id != contract.get("legacy_document_id")
                or document.content_hash != contract.get("legacy_content_hash")
            ):
                raise PermissionError("Legacy document hash mismatch")

            if (
                document.content_version != VERSION
                or document.case_id != "CASE-001"
                or document.family != "evidence"
                or document.access_scope != "collected_evidence"
                or document.required_ending is not None
                or document.protected_fact_ids
                or eid not in document.required_evidence
            ):
                raise PermissionError("Unsafe evidence document")

            if contract["score"] != resources.evidence_rules[eid].score:
                raise ValueError("Published score mismatch")

            requirements = django.get_evidence_requirements("CASE-001", eid)

            if sorted(requirements.prerequisites) != sorted(
                contract["required_evidence"]
            ):
                raise ValueError("Prerequisite mismatch")

            policy = policies[document.policy_id]

            if eid not in policy.required_evidence:
                raise PermissionError("Missing evidence access gate")

            # Prevent publication of unrelated documents or NPC cards.
            policy_users = sum(
                item.policy_id == document.policy_id for item in documents
            ) + sum(card.get("policy_id") == document.policy_id for card in cards)

            if policy_users != 1:
                raise PermissionError("Shared publication policy")

            policy_data = policy.model_dump(mode="json")

            policy_data["required_flags"] = [
                flag for flag in policy.required_flags if flag != DRAFT_FLAG
            ]

            policies[document.policy_id] = AccessPolicy.model_validate(policy_data)

            doc_data = document.model_dump(mode="json")

            doc_data["required_flags"] = [
                flag for flag in document.required_flags if flag != DRAFT_FLAG
            ]

            updated.append(PlayerDocument.model_validate(doc_data))

            published_ids.add(eid)

        if published_ids != set(approved):
            raise ValueError("Published RAG coverage mismatch")

        published_cards = activate_published_npc_cards(
            manifest=manifest,
            documents=documents,
            cards=cards,
            policies=policies,
            django=django,
            dataset_root=dataset_root,
        )

        published_holders = {
            eid
            for eid, contract in approved.items()
            if not contract["required_evidence"]
            and eid not in PROTECTED_IDS
        }

        if validate_e26_holder_approval(manifest):
            if "E26" not in published_ids:
                raise PermissionError(
                    "E26 document publication required"
                )

            published_holders.add("E26")

        published_resources = replace(
            resources,
            documents=tuple(updated),
            npc_cards=published_cards,
            published_holder_ids=tuple(
                sorted(published_holders)
            ),
            evaluator=PolicyEvaluator(policies),
        )

        print("DJANGO URL:", BASE_URL)
        print("RELEASE VERSION:", release_version)
        print("PUBLISHED EVIDENCE:", sorted(published_ids))
        print("PUBLISHED DOCUMENTS:", len(published_ids))
        print("UNPUBLISHED DOCUMENTS:", len(documents) - len(published_ids))
        print("RELEASE RUNTIME READY")

        yield published_resources
