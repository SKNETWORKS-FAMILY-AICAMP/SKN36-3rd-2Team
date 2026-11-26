"""Issue #191 - Protected ending image service."""

import os
from pathlib import Path
from types import MappingProxyType

from fastapi import HTTPException
from pydantic import BaseModel

from crimescene.scenario.schemas.game_state import GamePhase, GameState


IMAGE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}

ENDING_IMAGES = MappingProxyType({
    "NO_EVIDENCE": (),
    "UNSOLVED": ("escaped.png",),
    "ESTIMATED": (),
    "FULL": (),
    "DEEP": (
        "deep_album_blank.png",
        "deep_album_filled.png",
    ),
})


class EndingImageItem(BaseModel):
    index: int
    url: str


class EndingImagesResponse(BaseModel):
    endingCode: str
    images: list[EndingImageItem]


def image_unavailable() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail="Ending image unavailable",
        headers=dict(IMAGE_HEADERS),
    )


def get_ending_image_names(state: GameState) -> tuple[str, ...]:
    """Select images exclusively from verified server state."""

    if (
        not isinstance(state, GameState)
        or state.case_id != "CASE-001"
        or state.content_version != "case001_1120"
    ):
        raise image_unavailable()

    if state.phase != GamePhase.FINISHED:
        raise HTTPException(
            status_code=409,
            detail="Ending unavailable",
            headers=dict(IMAGE_HEADERS),
        )

    code = state.ending_code

    if code is None or code not in ENDING_IMAGES:
        raise image_unavailable()

    return ENDING_IMAGES[code]


def get_image_directory() -> Path:
    raw = os.getenv(
        "CRIMESCENE_ENDING_IMAGE_DIR",
        ".local/case001_ending_images",
    )

    directory = Path(raw).expanduser()

    if not directory.is_absolute():
        backend_root = Path(__file__).resolve().parents[3]
        directory = backend_root / directory

    return directory.resolve()


def resolve_ending_image(
    state: GameState,
    image_index: int,
) -> Path:
    names = get_ending_image_names(state)

    if (
        type(image_index) is not int
        or image_index < 1
        or image_index > len(names)
    ):
        raise image_unavailable()

    try:
        directory = get_image_directory()

        # Client-controlled filenames are never accepted.
        candidate = directory / names[image_index - 1]

        resolved = candidate.resolve(strict=True)

        # Reject path escape and symbolic links to other files.
        if (
            not resolved.is_relative_to(directory)
            or resolved != candidate
            or not resolved.is_file()
        ):
            raise image_unavailable()

        return resolved

    except (OSError, RuntimeError, ValueError):
        raise image_unavailable() from None


def build_ending_images_response(
    state: GameState,
) -> EndingImagesResponse:
    names = get_ending_image_names(state)

    images = []

    for index in range(1, len(names) + 1):
        # Do not advertise missing or unsafe image files.
        resolve_ending_image(state, index)

        images.append(
            EndingImageItem(
                index=index,
                url=(
                    f"/api/games/{state.session_id}"
                    f"/ending/images/{index}"
                ),
            )
        )

    return EndingImagesResponse(
        endingCode=state.ending_code,
        images=images,
    )
