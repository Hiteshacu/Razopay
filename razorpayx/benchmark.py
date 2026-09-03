"""Measure the detector on a held-out set, and report what it costs when wrong.

The track asks for precision and recall on a held-out test set, and for the
false-positive cost to be stated rather than buried. Both halves matter here
for a reason specific to this product: the expensive mistake is not missing a
forgery, it is calling a real payment fake. A missed forgery costs one
consignment of goods. A false accusation tells an honest payer their genuine
advice is a fraud, in front of the vendor they are trying to pay.

Held out means the thresholds and the reader's alphabets were fixed on a
development split and never refitted on the evaluation split. The two splits
use disjoint random seeds, so no advice appears in both.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from utils import read_image

from .adversary import fabricate, forge, journeys
from .advice import sample_advice
from .check import ALTERED, GENUINE, NOT_ISSUED, UNREADABLE, check
from .issue import issue


@dataclass
class Case:
    """One image put in front of the detector, and what it really was."""

    kind: str            # "genuine" or "forged"
    label: str           # which journey, or which forgery
    payout_id: str
    verdict: str
    detail: str = ""


@dataclass
class Report:
    cases: list[Case] = field(default_factory=list)

    # Two different questions, kept apart because conflating them flatters the
    # result. "Was the vendor protected" is whether the document was rejected
    # at all. "Did we explain it correctly" is whether we said *edited* rather
    # than *unsigned*.
    #
    # A forgery frequently comes back NOT_ISSUED rather than ALTERED, and that
    # is the watermark behaving correctly rather than failing: repainting a
    # 62px band across the page destroys the carrier blocks under it, so the
    # payload cannot be recovered at all. The vendor is told not to release
    # goods either way, which is the outcome that matters. But the attribution
    # is wrong, and reporting only the combined figure would hide that.
    @property
    def attributed(self) -> int:
        """Forgeries correctly identified as an edit to a real advice."""
        return sum(1 for c in self.cases if c.kind == "forged" and c.verdict == ALTERED)

    @property
    def rejected_as_unsigned(self) -> int:
        """Forgeries rejected, but explained as never issued."""
        return sum(1 for c in self.cases if c.kind == "forged" and c.verdict == NOT_ISSUED)

    @property
    def caught(self) -> int:
        """Forgeries the vendor was warned about, however explained."""
        return self.attributed + self.rejected_as_unsigned

    @property
    def missed(self) -> int:
        """Forgeries waved through as genuine. The dangerous failure."""
        return sum(1 for c in self.cases if c.kind == "forged" and c.verdict == GENUINE)

    @property
    def forged_unreadable(self) -> int:
        return sum(1 for c in self.cases if c.kind == "forged" and c.verdict == UNREADABLE)

    @property
    def forged_total(self) -> int:
        return sum(1 for c in self.cases if c.kind == "forged")

    @property
    def false_accusations(self) -> int:
        """Genuine advices called forged. The expensive mistake."""
        return sum(1 for c in self.cases if c.kind == "genuine" and c.verdict == ALTERED)

    @property
    def genuine_passed(self) -> int:
        return sum(1 for c in self.cases if c.kind == "genuine" and c.verdict == GENUINE)

    @property
    def genuine_unreadable(self) -> int:
        return sum(1 for c in self.cases if c.kind == "genuine" and c.verdict == UNREADABLE)

    @property
    def genuine_unsigned(self) -> int:
        """Genuine advices whose embedded signature did not survive the trip."""
        return sum(1 for c in self.cases if c.kind == "genuine" and c.verdict == NOT_ISSUED)

    @property
    def genuine_total(self) -> int:
        return sum(1 for c in self.cases if c.kind == "genuine")

    @property
    def precision(self) -> float:
        flagged = self.caught + self.false_accusations
        return self.caught / flagged if flagged else 0.0

    @property
    def recall(self) -> float:
        return self.caught / self.forged_total if self.forged_total else 0.0

    @property
    def attribution_rate(self) -> float:
        return self.attributed / self.forged_total if self.forged_total else 0.0

    @property
    def false_positive_rate(self) -> float:
        return self.false_accusations / self.genuine_total if self.genuine_total else 0.0


def _keys(directory: Path) -> tuple[Path, Path, str]:
    directory.mkdir(parents=True, exist_ok=True)
    private, public = directory / "priv.pem", directory / "pub.pem"
    if not private.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        public.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return private, public, public.read_text(encoding="utf-8")


def run(
    workdir: str | Path,
    *,
    advices: int = 8,
    seed: int = 1000,
    skip_watermark: bool = False,
    progress: bool = True,
) -> Report:
    """Issue `advices` advices, put every copy and every forgery through the
    detector, and total up what happened."""
    work = Path(workdir)
    private, public, public_pem = _keys(work / "keys")
    report = Report()

    for index in range(advices):
        rng = random.Random(seed + index)
        advice = sample_advice(rng)
        issued = issue(advice, work / "issued", private_key=private,
                       public_key=public, seed=seed + index)
        if progress:
            print(f"  [{index + 1}/{advices}] {advice.payout_id}  "
                  f"Rs {advice.amount_text} {advice.mode}", flush=True)

        for label, path in journeys(issued.image_path, work / "journeys"):
            verdict = check(read_image(path), path, issued.printed, public_pem,
                            skip_watermark=skip_watermark)
            report.cases.append(Case("genuine", label, advice.payout_id,
                                     verdict.status, verdict.detail))

        fabricated = fabricate(advice, work / "fabricated", seed + index)
        verdict = check(read_image(fabricated), fabricated, issued.printed,
                        public_pem, skip_watermark=skip_watermark)
        report.cases.append(Case("forged", "fabricated from scratch",
                                 advice.payout_id, verdict.status, verdict.detail))

        for forgery in forge(issued.image_path, advice, work / "forged", rng):
            # A forger sends the edited advice on through the same channels a
            # real one travels, so each forgery is measured after a messaging
            # app has been over it too, not only pristine.
            for label, path in journeys(forgery.path, work / "forged_journeys"):
                if label not in ("original", "whatsapp 960/q46", "jpeg q75"):
                    continue
                verdict = check(read_image(path), path, issued.printed, public_pem,
                                skip_watermark=skip_watermark)
                report.cases.append(Case("forged", f"{forgery.name} / {label}",
                                         advice.payout_id, verdict.status,
                                         verdict.detail))
    return report


def summarise(report: Report) -> str:
    lines = [
        "",
        "=" * 66,
        "  PAYOUT ADVICE FORGERY DETECTION - HELD-OUT RESULTS",
        "=" * 66,
        "",
        f"  Genuine advices tested : {report.genuine_total}",
        f"  Forged advices tested  : {report.forged_total}",
        "",
        "  FORGERIES",
        f"    rejected (vendor warned)   {report.caught:4}  / {report.forged_total}",
        f"      - named as edited        {report.attributed:4}      correct attribution",
        f"      - named as unsigned      {report.rejected_as_unsigned:4}      right call, wrong reason",
        f"    WAVED THROUGH              {report.missed:4}      <- the dangerous failure",
        f"    refused to answer          {report.forged_unreadable:4}",
        "",
        "  COST OF BEING WRONG",
        f"    genuine passed             {report.genuine_passed:4}  / {report.genuine_total}",
        f"    genuine FALSELY ACCUSED    {report.false_accusations:4}      <- the expensive one",
        f"    genuine unreadable         {report.genuine_unreadable:4}      <- asked for a better copy",
        f"    genuine signature lost     {report.genuine_unsigned:4}      <- watermark did not survive",
        "",
        f"  Precision            {report.precision:.3f}   flagged that were truly forged",
        f"  Recall               {report.recall:.3f}   forgeries rejected",
        f"  Attribution rate     {report.attribution_rate:.3f}   forgeries correctly explained",
        f"  False-positive rate  {report.false_positive_rate:.3f}   genuine advices falsely accused",
        "",
    ]
    return "\n".join(lines)


def breakdown(report: Report) -> str:
    """Per-case detail, so a bad number can be traced to what caused it."""
    by_label: dict[tuple[str, str], list[str]] = {}
    for case in report.cases:
        by_label.setdefault((case.kind, case.label), []).append(case.verdict)

    lines = ["  BY CASE", ""]
    for (kind, label), verdicts in sorted(by_label.items()):
        counts: dict[str, int] = {}
        for verdict in verdicts:
            counts[verdict] = counts.get(verdict, 0) + 1
        summary = "  ".join(f"{v}:{c}" for v, c in sorted(counts.items()))
        lines.append(f"    {kind:8} {label:40} {summary}")
    return "\n".join(lines) + "\n"


def to_json(report: Report, path: str | Path) -> None:
    Path(path).write_text(json.dumps({
        "precision": report.precision,
        "recall": report.recall,
        "false_positive_rate": report.false_positive_rate,
        "genuine_total": report.genuine_total,
        "forged_total": report.forged_total,
        "caught": report.caught,
        "missed": report.missed,
        "false_accusations": report.false_accusations,
        "cases": [vars(c) for c in report.cases],
    }, indent=2), encoding="utf-8")
