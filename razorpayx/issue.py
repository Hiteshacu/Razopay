"""Issue a signed payout advice, and keep the record needed to check it later.

Issuance does three things, in this order:

  1. Render the advice from the payout record.
  2. Embed a Trust Shield signature in the pixels. This is what proves the
     image came from RazorpayX and was not fabricated wholesale, and it is
     what survives a screenshot.
  3. Record the values that were printed, so a later read of the document has
     something authoritative to disagree with.

Step 3 is the one that closes the gap step 2 leaves open. The embedded
signature commits to a whole-page perceptual fingerprint whose tolerance —
the same tolerance that lets it survive recompression — is wider than a
repainted amount. Measured on this document: changing 29,30,217 to 99,30,217
touches 1.98% of the page and still verifies AUTHENTIC. The printed values
have to be committed to separately or that edit is invisible.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .advice import PayoutAdvice, field_text, render
from .layout import FIELDS


@dataclass(frozen=True)
class IssuedAdvice:
    """A signed advice and everything needed to verify it later."""

    payout_id: str
    image_path: Path
    #: field name -> exactly the string that was printed
    printed: dict[str, str]
    signature: str
    issued_at: str

    def to_record(self) -> dict:
        record = asdict(self)
        record["image_path"] = str(self.image_path)
        return record


def _sign(source: Path, destination: Path, private_key: Path, public_key: Path) -> str:
    """Embed the signature, returning it.

    SIGN_SELF_CHECK is forced to "fast" for the duration. The engine's default
    also simulates a messaging-app round trip before it will hand back a
    signed file, which is a useful guarantee for a poster and the wrong
    trade here: it roughly quadruples issuance time, and a payments API
    issuing advices synchronously cannot spend that per document.
    """
    previous = os.environ.get("SIGN_SELF_CHECK")
    os.environ["SIGN_SELF_CHECK"] = "fast"
    try:
        from sign_poster import sign_poster

        signature, _ = sign_poster(
            source, destination,
            private_key_path=private_key, public_key_path=public_key,
            self_check=True,
        )
    finally:
        if previous is None:
            os.environ.pop("SIGN_SELF_CHECK", None)
        else:
            os.environ["SIGN_SELF_CHECK"] = previous
    return signature if isinstance(signature, str) else str(signature)


def issue(
    advice: PayoutAdvice,
    directory: str | Path,
    *,
    private_key: str | Path,
    public_key: str | Path,
    seed: int = 0,
) -> IssuedAdvice:
    """Render, sign, and record one advice."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    unsigned = out / f"{advice.payout_id}_unsigned.png"
    signed = out / f"{advice.payout_id}.png"

    render(advice, unsigned, seed=seed)
    signature = _sign(unsigned, signed, Path(private_key), Path(public_key))
    unsigned.unlink(missing_ok=True)

    printed = {spec.name: field_text(advice, spec) for spec in FIELDS}
    issued = IssuedAdvice(
        payout_id=advice.payout_id,
        image_path=signed,
        printed=printed,
        signature=signature,
        issued_at=datetime.now().isoformat(timespec="seconds"),
    )
    (out / f"{advice.payout_id}.json").write_text(
        json.dumps(issued.to_record(), indent=2), encoding="utf-8"
    )
    return issued


def load_record(path: str | Path) -> IssuedAdvice:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["image_path"] = Path(data["image_path"])
    return IssuedAdvice(**data)
