"""trustshield — put a real signature inside a document's pixels.

    import trustshield

    keys = trustshield.KeyPair.generate().save("./keys")
    trustshield.sign("notice.png", "signed.png", private_key="./keys")
    print(trustshield.verify("signed.png", public_key="./keys"))
    # AUTHENTIC: Signature valid and content unchanged.

The signature is written into the image's frequency coefficients rather than
its metadata, so it survives being screenshotted, recompressed and forwarded
— all of which strip metadata completely.
"""

from __future__ import annotations

import os
from pathlib import Path

# The engine writes a registry and audit trail beside itself unless told
# otherwise. Inside an installed package that would mean writing into
# site-packages: unwritable in most deployments, and shared between every
# project on the machine when it is not. Point it at the user's own directory
# before the engine is imported, since it reads this at import time.
#
# Set DTS_DATA_DIR yourself to override — a per-project path is a good idea if
# you want each project's registry kept separate.
if not os.getenv("DTS_DATA_DIR"):
    default_data_dir = Path(
        os.getenv("XDG_DATA_HOME")
        or os.getenv("LOCALAPPDATA")
        or (Path.home() / ".local" / "share")
    ) / "trustshield"
    default_data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DTS_DATA_DIR"] = str(default_data_dir)

from .api import (  # noqa: E402  (must follow the DTS_DATA_DIR setup above)
    AUTHENTIC,
    ERROR,
    SIGNATURE_INVALID,
    TAMPERED,
    WATERMARK_NOT_FOUND,
    SignResult,
    SigningError,
    VerifyResult,
    sign,
    verify,
)
from .keys import KeyPair, load_private_key, load_public_key  # noqa: E402

__version__ = "0.1.0"

__all__ = [
    "KeyPair",
    "sign",
    "verify",
    "SignResult",
    "VerifyResult",
    "SigningError",
    "load_private_key",
    "load_public_key",
    "AUTHENTIC",
    "TAMPERED",
    "SIGNATURE_INVALID",
    "WATERMARK_NOT_FOUND",
    "ERROR",
    "__version__",
]


def data_dir() -> Path:
    """Where the engine keeps its registry and audit trail."""
    return Path(os.environ["DTS_DATA_DIR"])
