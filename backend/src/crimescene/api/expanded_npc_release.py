"""Issue #165 - approved NPC knowledge publication."""

import csv
import hashlib
import json

from crimescene.scenario.schemas.access_policy import AccessPolicy

VERSION = "case001_1120"
DRAFT_FLAG = "INTERNAL_DRAFT_NOT_PUBLISHED"


def digest_json(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def activate_published_npc_cards(
    *,
    manifest,
    documents,
    cards,
    policies,
    django,
    dataset_root,
):
    approved = manifest.get("approved_npc_cards", {})

    if not isinstance(approved, dict):
        raise TypeError("Invalid NPC release manifest")

    if not approved:
        return tuple(cards)

    source_files = list(
        (dataset_root.parent / "case001_1120_source")
        .rglob("08_NPC_KNOWLEDGE_CARDS.csv")
    )

    if len(source_files) != 1:
        raise ValueError("NPC source file mismatch")

    source_hash = hashlib.sha256(
        source_files[0].read_bytes()
    ).hexdigest()

    with source_files[0].open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        source_rows = {
            row["card_id"]: row
            for row in csv.DictReader(file)
        }

    published = set()
    updated = []
    remote_cards = {}

    for card in cards:
        cid = card["id"]

        if cid not in approved:
            updated.append(card)
            continue

        contract = approved[cid]
        npc_id = card["character_id"]
        policy_id = card["policy_id"]

        if (
            contract["card_id"] != cid
            or contract["character_id"] != npc_id
            or contract["content_version"] != VERSION
            or contract["scope"] != "LOCAL_INTEGRATION_TEST"
            or contract["policy_id"] != policy_id
            or contract["source_sha256"] != source_hash
            or not cid.startswith(f"K-{npc_id}-")
            or card["case_id"] != "CASE-001"
        ):
            raise PermissionError("NPC publication mismatch")

        body_hash = hashlib.sha256(
            card["body"].encode("utf-8")
        ).hexdigest()

        if body_hash != contract["body_sha256"]:
            raise ValueError("NPC body hash mismatch")

        if npc_id not in remote_cards:
            response = django.get_approved_npc_cards(
                "CASE-001",
                npc_id,
            )

            if response.character_id != npc_id:
                raise PermissionError("NPC response mismatch")

            remote_cards[npc_id] = {
                item.card_id: item.content
                for item in response.cards
                if item.card_type == "KNOWLEDGE"
            }

        if remote_cards[npc_id].get(cid) != card["body"]:
            raise PermissionError("NPC card is not approved")

        policy = policies[policy_id]

        if digest_json(
            policy.model_dump(mode="json")
        ) != contract["policy_sha256"]:
            raise ValueError("NPC policy hash mismatch")

        row = source_rows[cid]

        if (
            row["npc_id"] != npc_id
            or row["\ub0b4\uc6a9"].strip() != card["body"]
            or row["\uacf5\uac1c\uc870\uac74"]
            != contract["source_condition"]
        ):
            raise PermissionError("NPC source row mismatch")

        mode = contract.get("release_mode", "INITIAL")

        if mode == "INITIAL":
            if row["\uacf5\uac1c\uc870\uac74"] != "\ucc98\uc74c\ubd80\ud130":
                raise PermissionError(
                    "Unreviewed initial disclosure condition"
                )

            if any((
                policy.required_evidence,
                policy.required_presentations,
                policy.required_topics,
                policy.required_disclosed_cards,
                policy.required_ending,
                policy.required_npc_stage not in (None, 1),
            )):
                raise PermissionError(
                    "Invalid initial NPC policy"
                )

        elif mode == "AFTER_PRESENTATION":
            eid = contract["presentation_evidence_id"]
            presentation = f"{npc_id}:{eid}"

            if (
                eid not in manifest["approved_evidence"]
                or eid in {"E26", "E30"}
                or row["\uacf5\uac1c\uc870\uac74"] != f"P:{eid}"
                or set(policy.required_presentations)
                != {presentation}
                or not set(policy.required_evidence)
                .issubset({eid})
                or policy.required_topics
                or policy.required_disclosed_cards
                or policy.required_ending is not None
                or policy.required_npc_stage not in (None, 1, 2)
            ):
                raise PermissionError(
                    "Invalid presentation NPC policy"
                )

        else:
            raise PermissionError("Unknown NPC release mode")

        if policy.required_character != npc_id:
            raise PermissionError("NPC ownership mismatch")

        if set(policy.required_flags) != {DRAFT_FLAG}:
            raise PermissionError("Unexpected NPC policy flags")

        if set(card["required_flags"]) != {DRAFT_FLAG}:
            raise PermissionError("Unexpected card flags")

        policy_users = sum(
            item["policy_id"] == policy_id
            for item in cards
        ) + sum(
            item.policy_id == policy_id
            for item in documents
        )

        if policy_users != 1:
            raise PermissionError("Shared NPC policy")

        policy_data = policy.model_dump(mode="json")
        policy_data["required_flags"] = []

        policies[policy_id] = AccessPolicy.model_validate(
            policy_data
        )

        updated.append({
            **card,
            "required_flags": [],
        })

        published.add(cid)

    if published != set(approved):
        raise ValueError("Published NPC coverage mismatch")

    print("PUBLISHED NPC CARDS:", sorted(published))
    print("BLOCKED NPC CARDS:", len(cards) - len(published))

    return tuple(updated)
