
"""CASE-001 스토리 이벤트 검토표 검증 및 안전한 등록."""

import csv
import io
import re
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.content.models import Case, Chapter, Evidence, Scene, StoryEvent


COLUMNS = (
    "create_event",
    "evidence_id",
    "evidence_name",
    "holder_character_id",
    "required_evidence_ids",
    "chapter",
    "scene_id",
    "event_key",
    "event_title",
    "event_text",
    "review_status",
)

EVIDENCE_PATTERN = re.compile(r"E(?:0[1-9]|[12][0-9]|30)")
EVENT_PATTERN = re.compile(r"EVT-CH0[0-4]-[0-9]{3}")
EXPECTED_EVIDENCE = {f"E{i:02d}" for i in range(1, 31)}


def load_review_file(path: Path):
    """CSV를 읽고 검토 완료된 이벤트 정의만 선별합니다."""

    try:
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise CommandError("CSV 파일이 없거나 크기 제한을 초과했습니다.")

        raw = path.read_bytes()
        reader = csv.DictReader(
            io.StringIO(raw.decode("utf-8-sig"), newline="")
        )

        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise CommandError("검토표 컬럼 구조가 일치하지 않습니다.")

        rows = list(reader)

    except (OSError, UnicodeError, csv.Error) as exc:
        raise CommandError("CSV 파일을 읽을 수 없습니다.") from exc

    if len(rows) != 30:
        raise CommandError("증거 검토표는 정확히 30행이어야 합니다.")

    normalized = []
    selected = []
    selected_event_keys = set()

    for line_number, raw_row in enumerate(rows, start=2):
        if None in raw_row or any(
            value is None for value in raw_row.values()
        ):
            raise CommandError(f"{line_number}행: 잘못된 CSV 구조입니다.")

        row = {
            key: value.strip()
            for key, value in raw_row.items()
        }

        normalized.append(row)
        selection = row["create_event"]
        review = row["review_status"]

        if selection not in {"YES", "NO"}:
            raise CommandError(f"{line_number}행: YES 또는 NO만 허용됩니다.")

        if review not in {"PENDING", "REVIEWED"}:
            raise CommandError(f"{line_number}행: 검토 상태가 잘못되었습니다.")

        if selection == "NO":
            continue

        if review != "REVIEWED":
            raise CommandError(
                f"{line_number}행: 검토되지 않은 이벤트는 등록할 수 없습니다."
            )

        chapter = row["chapter"]
        event_key = row["event_key"]
        scene_id = row["scene_id"]

        if (
            chapter not in {"CH00", "CH01", "CH02", "CH03", "CH04"}
            or EVENT_PATTERN.fullmatch(event_key) is None
            or not event_key.startswith(f"EVT-{chapter}-")
            or re.fullmatch(r"SC-[0-9]{4}", scene_id) is None
        ):
            raise CommandError(
                f"{line_number}행: 챕터·이벤트·장면 ID가 잘못되었습니다."
            )

        if event_key in selected_event_keys:
            raise CommandError(f"{line_number}행: 중복 이벤트 ID입니다.")

        selected_event_keys.add(event_key)

        required = row["required_evidence_ids"].split("|")

        if (
            not 1 <= len(required) <= 30
            or any(
                EVIDENCE_PATTERN.fullmatch(item) is None
                for item in required
            )
            or len(required) != len(set(required))
            or row["evidence_id"] not in required
        ):
            raise CommandError(
                f"{line_number}행: 필수 증거 조건이 잘못되었습니다."
            )

        if (
            not 1 <= len(row["event_title"]) <= 120
            or not 1 <= len(row["event_text"]) <= 5000
        ):
            raise CommandError(
                f"{line_number}행: 스토리 제목 또는 본문이 잘못되었습니다."
            )

        row["parsed_required_evidence"] = required
        selected.append(row)

    if {row["evidence_id"] for row in normalized} != EXPECTED_EVIDENCE:
        raise CommandError("증거 E01~E30의 누락 또는 중복이 있습니다.")

    return normalized, selected


class Command(BaseCommand):
    help = "검토 완료된 CASE-001 스토리 이벤트를 안전하게 등록합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            required=True,
            type=Path,
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="DB 반영. 기본값은 Dry Run입니다.",
        )

    def handle(self, *args, **options):
        rows, selected = load_review_file(options["source"])

        created = 0
        existing = 0

        try:
            with transaction.atomic():
                case = Case.objects.filter(
                    case_id="CASE-001"
                ).first()

                if case is None or case.status != Case.Status.DRAFT:
                    raise CommandError(
                        "CASE-001이 없거나 DRAFT 상태가 아닙니다."
                    )

                evidence_map = {
                    item.evidence_id: item
                    for item in Evidence.objects.filter(case=case)
                    .select_related("holder")
                }

                if set(evidence_map) != EXPECTED_EVIDENCE:
                    raise CommandError("CASE-001 증거 데이터가 불완전합니다.")

                # 검토표가 실제 DB와 동일한 증거를 참조하는지 확인
                for row in rows:
                    evidence = evidence_map[row["evidence_id"]]
                    holder_id = (
                        evidence.holder.character_id
                        if evidence.holder_id else ""
                    )

                    if (
                        row["evidence_name"] != evidence.name
                        or row["holder_character_id"] != holder_id
                    ):
                        raise CommandError(
                            f"증거 원본과 검토표가 불일치합니다: "
                            f"{row['evidence_id']}"
                        )

                chapters = {
                    item.code: item
                    for item in Chapter.objects.filter(case=case)
                }
                scenes = {
                    item.scene_id: item
                    for item in Scene.objects.filter(case=case)
                    .select_related("chapter")
                }

                for row in selected:
                    chapter = chapters.get(row["chapter"])
                    scene = scenes.get(row["scene_id"])

                    if (
                        chapter is None
                        or scene is None
                        or scene.chapter_id != chapter.pk
                    ):
                        raise CommandError(
                            f"챕터·장면 연결이 잘못되었습니다: "
                            f"{row['event_key']}"
                        )

                    for evidence_id in row["parsed_required_evidence"]:
                        if evidence_id not in evidence_map:
                            raise CommandError(
                                f"존재하지 않는 증거입니다: {evidence_id}"
                            )

                    expected = {
                        "chapter": chapter,
                        "trigger_type": (
                            StoryEvent.TriggerType.EVIDENCE_COLLECTED
                        ),
                        "conditions": {
                            "requiredEvidenceIds": (
                                row["parsed_required_evidence"]
                            ),
                        },
                        "payload": {
                            "title": row["event_title"],
                            "text": row["event_text"],
                        },
                        "metadata": {
                            "source_scene_id": row["scene_id"],
                            "source_evidence_id": row["evidence_id"],
                            "review_status": "REVIEWED",
                            "runtime_enabled": False,
                            "backend_contract_approved": False,
                        },
                    }

                    event = StoryEvent.objects.filter(
                        event_key=row["event_key"]
                    ).first()

                    if event is not None:
                        if any(
                            getattr(event, key) != value
                            for key, value in expected.items()
                        ):
                            raise CommandError(
                                f"기존 이벤트와 충돌합니다: {row['event_key']}"
                            )

                        existing += 1
                        continue

                    event = StoryEvent(
                        event_key=row["event_key"],
                        **expected,
                    )
                    event.full_clean()
                    event.save()
                    created += 1

                self.stdout.write(
                    f"Reviewed events: {len(selected)}"
                )
                self.stdout.write(f"New events: {created}")
                self.stdout.write(f"Existing events: {existing}")

                if not options["apply"]:
                    transaction.set_rollback(True)

        except (ValidationError, IntegrityError) as exc:
            raise CommandError(
                "스토리 이벤트 데이터 검증에 실패했습니다."
            ) from exc

        if options["apply"]:
            self.stdout.write(self.style.SUCCESS("IMPORT COMMITTED"))
        else:
            self.stdout.write(
                self.style.WARNING("DRY RUN - NO CHANGES COMMITTED")
            )
