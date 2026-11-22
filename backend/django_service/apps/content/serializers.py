
"""CASE-001 콘텐츠 API 직렬화 계층."""

from rest_framework import serializers

from .models import Case, Chapter


class CaseSummarySerializer(serializers.ModelSerializer):
    """사건의 기본 관리 정보만 직렬화합니다."""

    class Meta:
        model = Case
        fields = (
            "case_id",
            "title",
            "status",
        )
        read_only_fields = fields


class ChapterSummarySerializer(serializers.ModelSerializer):
    """챕터의 기본 정보만 직렬화합니다."""

    class Meta:
        model = Chapter
        fields = (
            "code",
            "order",
            "title",
        )
        read_only_fields = fields
