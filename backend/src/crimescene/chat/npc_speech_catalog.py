"""Version-bound local NPC speech catalog."""

import hashlib
import hmac
import json
import os
import re

from functools import lru_cache
from pathlib import Path
from types import MappingProxyType


MAX_CATALOG_BYTES = 512 * 1024

NPC_PATTERN = re.compile(r"C(?:0[1-9]|10)")
SHA256_PATTERN = re.compile(r"[a-f0-9]{64}")


def reject_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")

        result[key] = value

    return result


@lru_cache(maxsize=2)
def load_speech_catalog(
    path: str,
    expected_sha256: str,
    release_version: str,
):

    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise ValueError("Invalid catalog digest")

    with Path(path).open("rb") as file:
        raw = file.read(MAX_CATALOG_BYTES + 1)

    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError("Catalog size limit exceeded")

    actual_digest = hashlib.sha256(raw).hexdigest()

    if not hmac.compare_digest(
        actual_digest,
        expected_sha256,
    ):
        raise ValueError("Catalog integrity mismatch")

    data = json.loads(
        raw,
        object_pairs_hook=reject_duplicate_keys,
    )

    if (
        not isinstance(data, dict)
        or set(data) != {
            "schema_version",
            "content_version",
            "release_version",
            "status",
            "entries",
        }
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or data["content_version"] != "case001_1120"
        or data["release_version"] != release_version
        or data["status"] != "LOCAL_TEST_ONLY"
    ):
        raise ValueError("Catalog metadata mismatch")

    entries = data["entries"]

    if (
        not isinstance(entries, list)
        or not 1 <= len(entries) <= 1000
    ):
        raise ValueError("Invalid entry count")

    mapping = {}

    for entry in entries:

        if (
            not isinstance(entry, dict)
            or set(entry) != {
                "character_id",
                "source_id",
                "quote",
                "speech",
            }
            or any(
                not isinstance(value, str)
                for value in entry.values()
            )
        ):
            raise ValueError("Invalid catalog entry")

        npc = entry["character_id"]
        source_id = entry["source_id"]
        quote = entry["quote"]
        speech = entry["speech"]

        if (
            not NPC_PATTERN.fullmatch(npc)
            or not re.fullmatch(
                rf"K-{npc}-\d{{2}}",
                source_id,
            )
        ):
            raise ValueError("NPC source mismatch")

        if (
            not 6 <= len(quote) <= 320
            or quote.splitlines() != [quote]
            or not 1 <= len(speech.strip()) <= 500
            or speech != speech.strip()
            or speech.splitlines() != [speech]
            or any(
                ord(char) < 32
                for char in quote + speech
            )
            or "(근거:" in speech
            or re.search(r"\b(?:K-C\d{2}-\d{2}|E\d{2})\b", speech)
        ):
            raise ValueError("Invalid speech content")

        key = (npc, source_id, quote)

        if key in mapping:
            raise ValueError("Duplicate speech mapping")

        mapping[key] = speech

    return MappingProxyType(mapping)


def configured_speech_catalog():

    path = os.getenv(
        "CRIMESCENE_LOCAL_SPEECH_CATALOG", ""
    ).strip()

    digest = os.getenv(
        "CRIMESCENE_LOCAL_SPEECH_SHA256", ""
    ).strip()

    if not path or not digest:
        return None

    return load_speech_catalog(
        str(Path(path).resolve()),
        digest,
        os.getenv(
            "CRIMESCENE_EXPANDED_RELEASE_VERSION",
            "v0.11.0",
        ).strip(),
    )
