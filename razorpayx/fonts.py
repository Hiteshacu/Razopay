"""Font resolution that works on a Windows laptop and in a slim Linux container.

The demo is developed on Windows and deployed to python:3.11-slim, which ships
no Segoe UI and no Arial. Rendering has to degrade to whatever is present
rather than raising, because a payout advice that fails to render is a demo
that fails to run in front of a judge.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# Ordered by preference. Windows first because that is where this is authored
# and where the screenshots come from; DejaVu next because Pillow bundles it
# and Debian slim usually has it; the bitmap default last so we never raise.
_REGULAR = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
_BOLD = (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
_MONO = (
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
)


def _first_present(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


@lru_cache(maxsize=64)
def font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    """A font at `size`, falling back through the lists above."""
    family = _MONO if mono else (_BOLD if bold else _REGULAR)
    path = _first_present(family)
    if path is None:
        # load_default ignores size on older Pillow; on 10+ it honours it.
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # pragma: no cover - very old Pillow
            return ImageFont.load_default()
    return ImageFont.truetype(path, size)
