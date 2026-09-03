"""Decide whether a payout advice in hand is the one RazorpayX issued.

Two independent checks, because they catch different frauds and neither
catches both.

  Watermark. Proves the image came from RazorpayX at all, and survives a
  screenshot. Catches wholesale fabrication — an advice invented in an image
  editor carries no signature. Blind to small edits: its perceptual
  fingerprint tolerates a repainted amount, by the same tolerance that lets
  it survive a messaging app.

  Field read. Compares the printed values against the record RazorpayX kept
  when it issued the advice. Catches the surgical edit the watermark misses,
  because a 9 that used to be a 2 is a different character no matter how few
  pixels changed.

A verdict of UNREADABLE is deliberate and is not a failure. The alternative
to admitting the copy is too degraded to read is guessing, and a guess that
comes out wrong accuses an honest payer of forgery. Asking for a clearer copy
costs a vendor thirty seconds; a false accusation costs them a customer.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .layout import CHECKED, Field
from .read import read_field

GENUINE = "GENUINE"
ALTERED = "ALTERED"
NOT_ISSUED = "NOT_ISSUED"
WRONG_KEY = "WRONG_KEY"
UNREADABLE = "UNREADABLE"


@dataclass
class FieldFinding:
    """What one field was supposed to say, and what it says now."""

    name: str
    expected: str
    read: str
    confidence: float
    matched: bool


@dataclass
class Verdict:
    """The answer, and the evidence behind it."""

    status: str
    headline: str
    detail: str
    watermark_ok: bool
    findings: list[FieldFinding] = field(default_factory=list)

    @property
    def altered_fields(self) -> list[str]:
        return [f.name for f in self.findings if not f.matched]


def _normalise(text: str, spec: Field) -> str:
    """Reduce a read and an expected value to comparable form.

    The reader is exact about characters and approximate about spacing and
    punctuation — a comma may segment as a speck, a decimal point may merge
    into a neighbouring stroke. Comparing raw strings would report those as
    forgeries. Comparing the characters that carry the value does not.
    """
    if spec.numeric:
        return re.sub(r"\D", "", text)
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _verify_watermark(image_path: Path, public_key_pem: str) -> tuple[bool, str]:
    """Ask the engine whether this image carries a valid signature."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="w") as handle:
        handle.write(public_key_pem)
        key_path = Path(handle.name)
    previous = os.environ.get("SIGN_SELF_CHECK")
    os.environ["SIGN_SELF_CHECK"] = "fast"
    try:
        from verify_poster import verify_poster

        outcome = verify_poster(image_path, public_key_path=key_path, audit=False)
        ok = outcome[0] if isinstance(outcome, tuple) else bool(outcome)
        return bool(ok), ""
    except Exception as exc:
        return False, str(exc)
    finally:
        key_path.unlink(missing_ok=True)
        if previous is None:
            os.environ.pop("SIGN_SELF_CHECK", None)
        else:
            os.environ["SIGN_SELF_CHECK"] = previous


def check(
    image: np.ndarray,
    image_path: Path,
    printed: dict[str, str],
    public_key_pem: str,
    *,
    skip_watermark: bool = False,
) -> Verdict:
    """Adjudicate one advice against the record RazorpayX kept.

    `skip_watermark` exists for measuring the field reader on its own. It is
    not exposed to callers of the API — a verdict that skipped the signature
    check would say "genuine" about an image nobody signed.
    """
    watermark_ok, engine_message = (True, "") if skip_watermark else _verify_watermark(
        image_path, public_key_pem
    )

    findings: list[FieldFinding] = []
    unreadable: list[str] = []
    for spec in CHECKED:
        expected = printed.get(spec.name, "")
        result = read_field(
            image, spec.box, size=spec.size, bold=spec.bold,
            alphabet=spec.alphabet, mono=spec.mono,
        )
        if not result.usable:
            unreadable.append(spec.name)
            continue
        got, want = _normalise(result.text, spec), _normalise(expected, spec)
        findings.append(
            FieldFinding(spec.name, expected, result.text, result.confidence, got == want)
        )

    changed = [f for f in findings if not f.matched]

    # Order matters. A document with a changed amount AND no signature is
    # reported as never issued, because that is the more fundamental fact and
    # the one that tells the vendor what to do.
    if not watermark_ok:
        if "did not validate" in engine_message.lower():
            return Verdict(
                WRONG_KEY,
                "Not signed by this RazorpayX account",
                "A signature is present but does not belong to the account you checked "
                "against. Confirm who the payer says they are.",
                False, findings,
            )
        return Verdict(
            NOT_ISSUED,
            "No RazorpayX signature found",
            "This image carries no embedded proof. RazorpayX did not issue it, or it "
            "has been damaged past recovery: a heavy crop, or a photo of a screen.",
            False, findings,
        )

    if changed:
        names = ", ".join(f.name.replace("_", " ") for f in changed)
        return Verdict(
            ALTERED,
            "Issued by RazorpayX, then edited",
            f"The signature is real. RazorpayX did issue this advice, but the "
            f"{names} printed on it no longer matches what was issued. "
            f"Do not release goods against this document.",
            True, findings,
        )

    if len(findings) < len(CHECKED):
        return Verdict(
            UNREADABLE,
            "Signature valid, but this copy is too degraded to check the figures",
            f"The embedded proof verified, so RazorpayX issued this advice. But "
            f"{', '.join(unreadable)} could not be read confidently enough to "
            f"compare. Ask for the original file rather than a forwarded photo.",
            True, findings,
        )

    return Verdict(
        GENUINE,
        "Genuine",
        "RazorpayX issued this advice, and every figure on it still matches what "
        "was issued. Note that NEFT and RTGS settle in batches, so the credit may "
        "not have reached the account yet.",
        True, findings,
    )
