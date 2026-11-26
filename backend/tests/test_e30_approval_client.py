"""Issue #192 - E30 consent approval client security tests."""

import httpx
import pytest

from crimescene.api.django_content_client import DjangoContentClient


CHECKSUM = "sha256:" + "a" * 64

REQUEST = {
    "case_id": "CASE-001",
    "release_version": "v0.15.0",
    "release_checksum": CHECKSUM,
    "review_version": "v0.99.0",
}

VALID_RESPONSE = {
    **REQUEST,
    "approved": True,
}


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, VALID_RESPONSE, True),
        (404, {}, False),
        (403, {}, False),
        (503, {}, False),
        (200, {}, False),
        (200, {**VALID_RESPONSE, "approved": False}, False),
        (200, {**VALID_RESPONSE, "approved": 1}, False),
        (200, {**VALID_RESPONSE, "case_id": "CASE-002"}, False),
        (200, {**VALID_RESPONSE, "release_version": "v0.1.0"}, False),
        (200, {**VALID_RESPONSE, "review_version": "v0.1.0"}, False),
        (200, {**VALID_RESPONSE, "release_checksum": "invalid"}, False),
        (200, {**VALID_RESPONSE, "unexpected": "data"}, False),
    ],
)
def test_e30_review_response_validation(status, body, expected):
    def handler(request):
        assert request.headers["X-Content-Service-Token"] == "x" * 40

        assert request.url.path == (
            "/api/content/internal/cases/CASE-001/releases/"
            "v0.15.0/e30-consent-reviews/v0.99.0/"
        )

        return httpx.Response(status, json=body)

    with DjangoContentClient(
        base_url="http://127.0.0.1:18004",
        token="x" * 40,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_e30_consent_approval(**REQUEST) is expected


def test_e30_review_timeout_denies_approval():
    def handler(request):
        raise httpx.ReadTimeout("Synthetic timeout", request=request)

    with DjangoContentClient(
        base_url="http://127.0.0.1:18004",
        token="x" * 40,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_e30_consent_approval(**REQUEST) is False


def test_e30_review_invalid_json_denies_approval():
    def handler(request):
        return httpx.Response(200, content=b"INVALID JSON")

    with DjangoContentClient(
        base_url="http://127.0.0.1:18004",
        token="x" * 40,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_e30_consent_approval(**REQUEST) is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"case_id": "CASE-002"},
        {"review_version": "../secret"},
        {"review_version": "v0.15.0"},
        {"release_checksum": "invalid"},
        {"release_version": "invalid"},
    ],
)
def test_invalid_e30_review_request_never_calls_django(overrides):
    def handler(request):
        pytest.fail("Invalid request reached Django")

    with DjangoContentClient(
        base_url="http://127.0.0.1:18004",
        token="x" * 40,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_e30_consent_approval(
            **{**REQUEST, **overrides}
        ) is False
