"""Forgeries and honest journeys, for measuring the detector.

Kept in one module, imported only by the benchmark, and deliberately not
reachable from the API or the CLI. Measuring recall means producing forgeries;
shipping a button that produces them would hand an attacker the one tool this
project exists to defeat, and the track this is built for disqualifies
anything offence-capable. Every forgery it makes lands on a page already
stamped SPECIMEN, because the renderer stamps before signing.

The forgeries are the ones that pay. A fraudster does not redraw a payout
advice; they change the number that decides whether goods leave the warehouse,
and they change nothing else, because everything else is what makes the
document look real.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .advice import BAND, INK, PAPER, PayoutAdvice, field_text
from .fonts import font
from .layout import BY_NAME, Field


@dataclass(frozen=True)
class Forgery:
    """One edit, and which field it lands on."""

    name: str
    field: str
    path: Path


def _repaint(image: Image.Image, spec: Field, text: str, *, left: int) -> None:
    """Paint over one field and write a different value in its place.

    Repainting rather than re-rendering the whole page on purpose: a forger
    works on the image they were given, so the forgery has to inherit the
    signed pixels everywhere except the field they touched. Re-rendering would
    also replace the embedded signature, which would make every forgery
    trivially detectable and the measurement worthless.
    """
    draw = ImageDraw.Draw(image)
    top, bottom = spec.top, spec.top + spec.height
    draw.rectangle([left - 8, top + 2, 940, bottom - 2],
                   fill=BAND if spec.shaded else PAPER)
    baseline = top + (spec.height - spec.size) // 2 - 2
    draw.text((left, baseline), text, font=font(spec.size, bold=spec.bold,
                                                mono=spec.mono), fill=INK)


def forge(
    signed_path: Path,
    advice: PayoutAdvice,
    out_dir: Path,
    rng: random.Random,
) -> list[Forgery]:
    """Every forgery worth testing against one issued advice."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Forgery] = []
    stem = signed_path.stem

    def start(spec: Field) -> Image.Image:
        return Image.open(signed_path).convert("RGB")

    # 1. Inflate the amount. The headline number and the table number are
    #    changed together, because a forger who changes one and not the other
    #    is caught by a human reading the page.
    inflated = advice.amount_paise * rng.choice((2, 3, 10))
    image = start(BY_NAME["hero_amount"])
    hero = BY_NAME["hero_amount"]
    _repaint(image, hero, f"Rs {inflated / 100:,.2f}", left=64)
    table = BY_NAME["table_amount"]
    _repaint(image, table, f"Rs {inflated / 100:,.2f}", left=430)
    path = out_dir / f"{stem}_amount.png"
    image.save(path)
    made.append(Forgery("amount inflated", "table_amount", path))

    # 2. Change only the headline, leaving the table row honest. Tests whether
    #    checking one amount field would have been enough.
    image = start(hero)
    _repaint(image, hero, f"Rs {inflated / 100:,.2f}", left=64)
    path = out_dir / f"{stem}_hero_only.png"
    image.save(path)
    made.append(Forgery("headline amount only", "hero_amount", path))

    # 3. Redirect the payment to a different beneficiary.
    image = start(BY_NAME["beneficiary"])
    _repaint(image, BY_NAME["beneficiary"], "Kaveri Textiles Pvt Ltd"
             if "Kaveri" not in advice.beneficiary_legal else "Nandini Foods Pvt Ltd",
             left=430)
    path = out_dir / f"{stem}_beneficiary.png"
    image.save(path)
    made.append(Forgery("beneficiary swapped", "beneficiary", path))

    # 4. Fabricate a UTR. A vendor who phones the bank quotes this number, so
    #    a plausible-looking wrong one buys the fraudster a day.
    image = start(BY_NAME["utr"])
    digits = "".join(rng.choices("0123456789", k=15))
    _repaint(image, BY_NAME["utr"], advice.utr[0] + digits, left=430)
    path = out_dir / f"{stem}_utr.png"
    image.save(path)
    made.append(Forgery("UTR fabricated", "utr", path))

    # 5. Change the last four of the destination account.
    image = start(BY_NAME["account"])
    other = "".join(rng.choices("0123456789", k=4))
    _repaint(image, BY_NAME["account"], f"XXXXXXXX{other}", left=430)
    path = out_dir / f"{stem}_account.png"
    image.save(path)
    made.append(Forgery("account digits changed", "account", path))

    # 6. The subtle one. A single digit, chosen so the amount still looks
    #    ordinary and the digit count does not change — 8,03,626 becomes
    #    8,03,826. Doubling an amount is what a greedy forger does; changing
    #    one digit is what a careful one does, and it is the case that
    #    decides whether this is a real detector or a demo.
    text = f"{advice.amount_paise / 100:,.2f}"
    digits = [i for i, ch in enumerate(text) if ch.isdigit()]
    position = digits[len(digits) // 2]
    swapped = "9" if text[position] != "9" else "4"
    nudged = text[:position] + swapped + text[position + 1:]
    image = start(hero)
    _repaint(image, hero, f"Rs {nudged}", left=64)
    _repaint(image, table, f"Rs {nudged}", left=430)
    path = out_dir / f"{stem}_one_digit.png"
    image.save(path)
    made.append(Forgery("single digit changed", "table_amount", path))

    return made


def fabricate(advice: PayoutAdvice, out_dir: Path, seed: int) -> Path:
    """An advice invented from scratch and never signed by RazorpayX.

    The other forgeries all start from a genuine issued file. This one does
    not, which is the case the embedded signature exists for: there is no
    watermark to recover, so it should be rejected as never issued no matter
    what the printed figures say.
    """
    from .advice import render

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{advice.payout_id}_fabricated.png"
    render(advice, path, seed=seed)
    return path


# --------------------------------------------------------------------------
# Honest journeys. What happens to a real advice on its way to a real vendor.
# --------------------------------------------------------------------------

def journeys(source: Path, out_dir: Path) -> list[tuple[str, Path]]:
    """Lossy but legitimate copies of an advice.

    Every one of these is a genuine document. Any of them that the detector
    calls forged is a false positive, and a false positive here means telling
    a vendor that a real payment is fake — so these are the cases that decide
    whether the thing is usable, not the forgeries.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    made: list[tuple[str, Path]] = [("original", source)]
    image = Image.open(source).convert("RGB")

    for quality in (92, 75, 55, 35):
        path = out_dir / f"{stem}_q{quality}.jpg"
        image.save(path, "JPEG", quality=quality)
        made.append((f"jpeg q{quality}", path))

    # A messaging app: downscale to 960 on the long edge, then a hard JPEG.
    forwarded = image.copy()
    forwarded.thumbnail((960, 960), Image.LANCZOS)
    path = out_dir / f"{stem}_whatsapp.jpg"
    forwarded.save(path, "JPEG", quality=46)
    made.append(("whatsapp 960/q46", path))

    # Someone screenshots the PDF viewer rather than saving the file.
    shot = image.resize((int(image.width * 0.78), int(image.height * 0.78)), Image.LANCZOS)
    shot = shot.filter(ImageFilter.GaussianBlur(0.4))
    path = out_dir / f"{stem}_screenshot.png"
    shot.save(path)
    made.append(("screenshot", path))

    # A photo of a screen rather than a screenshot: slight rotation, and the
    # softness a phone camera adds. This is the case the engine documents as
    # beyond recovery, and it is included so the failure is measured rather
    # than assumed.
    rotated = image.rotate(0.7, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    rotated = rotated.filter(ImageFilter.GaussianBlur(0.6))
    path = out_dir / f"{stem}_photo.jpg"
    rotated.save(path, "JPEG", quality=68)
    made.append(("photo of screen", path))

    # Downloaded, resized by an email client.
    for width in (820, 680):
        resized = image.resize((width, int(image.height * width / image.width)), Image.LANCZOS)
        path = out_dir / f"{stem}_w{width}.png"
        resized.save(path)
        made.append((f"resized {width}px", path))

    return made
