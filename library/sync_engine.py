"""Copy the engine modules into the package.

    cd library
    python sync_engine.py

The engine lives at the repository root, where the backend imports it. The
library ships the same modules inside `trustshield.engine` so that a wheel is
self-contained — a developer installing from PyPI has no repository.

Copying rather than importing across the two keeps one source of truth: the
root files are edited, this script republishes them. A second hand-maintained
copy would drift, and a drifted crypto implementation is the worst kind.

No source rewriting is needed. Every cross-module import in the engine is
already written as a relative import with an absolute fallback:

    try:
        from .utils import read_image
    except ImportError:
        from utils import read_image

so the same files resolve correctly as a flat script set at the root and as a
package here.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TARGET = HERE / "src" / "trustshield" / "engine"

MODULES = [
    "utils.py",
    "sign_poster.py",
    "verify_poster.py",
    "watermark_embedder.py",
    "watermark_extractor.py",
    "pdf_support.py",
    "video_support.py",
    "generate_keys.py",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    missing = [name for name in MODULES if not (ROOT / name).is_file()]
    if missing:
        print(f"Missing at the repository root: {', '.join(missing)}")
        return 1

    changed = 0
    for name in MODULES:
        source = ROOT / name
        destination = TARGET / name
        same = destination.is_file() and digest(destination) == digest(source)
        if not same:
            destination.write_bytes(source.read_bytes())
            changed += 1
        print(f"  {'copied ' if not same else 'current'}  {name:<26} {digest(source)}")

    print()
    print(f"{len(MODULES)} modules, {changed} updated -> {TARGET.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
