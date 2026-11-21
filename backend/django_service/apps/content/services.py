
"""콘텐츠 도메인의 비즈니스 로직을 담당합니다."""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Case, Evidence, EvidencePrerequisite


def create_evidence_prerequisite(
    *,
    dependent_id: int,
    prerequisite_id: int,
) -> EvidencePrerequisite:
    """동일 사건 내에서 순환이 없는 증거 선행 관계를 생성합니다."""

    # bool은 int의 하위 타입이므로 정확한 정수 타입을 확인합니다.
    for field_name, value in (
        ("dependent_id", dependent_id),
        ("prerequisite_id", prerequisite_id),
    ):
        if type(value) is not int or value <= 0:
            raise ValidationError({
                field_name: "1 이상의 정수 ID를 입력해야 합니다."
            })

    if dependent_id == prerequisite_id:
        raise ValidationError(
            "증거는 자기 자신을 선행 조건으로 가질 수 없습니다."
        )

    with transaction.atomic():
        evidence_map = {
            evidence.pk: evidence
            for evidence in Evidence.objects.filter(
                pk__in=(dependent_id, prerequisite_id)
            )
        }

        if len(evidence_map) != 2:
            raise ValidationError(
                "존재하지 않는 증거가 포함되어 있습니다."
            )

        dependent = evidence_map[dependent_id]
        prerequisite = evidence_map[prerequisite_id]

        if dependent.case_id != prerequisite.case_id:
            raise ValidationError(
                "서로 다른 사건의 증거를 연결할 수 없습니다."
            )

        # PostgreSQL 등 지원 DB에서 사건 단위 동시 수정을 직렬화합니다.
        Case.objects.select_for_update().get(pk=dependent.case_id)

        relation = EvidencePrerequisite(
            dependent=dependent,
            prerequisite=prerequisite,
        )

        # 기존 모델의 중복·자기참조·순환 관계 검증을 실행합니다.
        relation.full_clean()
        relation.save()

        return relation
