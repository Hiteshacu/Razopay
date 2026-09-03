"""Render a RazorpayX-style payout advice.

Why this document, and why it is the one worth signing
------------------------------------------------------
RazorpayX sends money by UPI, IMPS, NEFT and RTGS, and issues the payer a
payout advice they forward to the beneficiary as proof of payment. NEFT and
RTGS are not instant — they settle in batches, minutes to hours later. So a
vendor handed an advice has a real window where the money genuinely has not
arrived yet and no amount of checking their own bank tells them whether it is
coming. That window is where the fraud lives, and it is the window a soundbox
cannot close, because soundboxes announce UPI credits and these are not UPI.

Documented losses of exactly this shape: a Mumbai used-car dealer, 6.5 lakh,
against an edited NEFT slip printed on paper. Ranka Jewellers, 3.48 lakh of
gold, against a fabricated NEFT confirmation held up on a phone.

Every advice is marked SPECIMEN
-------------------------------
These are fixtures for a fraud-detection benchmark, not payment records. A
generator that emitted clean, unmarked RazorpayX advices would be a forgery
tool wearing a lab coat — useful to precisely the people this is built to
stop, and disqualifying under a defence-only rule. The marking is drawn into
the pixels before signing, so it survives into every signed artefact and
cannot be dropped by a caller who forgets a flag.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from .fonts import font
from .layout import FIELDS, HERO_AMOUNT, LEFT, SECTIONS, VALUE_X, Field

# RazorpayX's palette, approximately. Used to make the specimen look like the
# real thing at a glance, which is the whole point: a document that obviously
# looks fake would not test anything.
NAVY = (12, 31, 63)
BLUE = (51, 149, 255)
INK = (23, 33, 51)
MUTED = (110, 122, 142)
RULE = (223, 228, 236)
PAPER = (255, 255, 255)
BAND = (246, 248, 251)
GREEN = (11, 138, 90)
GREEN_WASH = (232, 246, 240)

WIDTH, HEIGHT = 1000, 1400

MODES = ("NEFT", "RTGS", "IMPS")

_BENEFICIARIES = (
    ("Sundar Traders", "Sundar Traders Pvt Ltd"),
    ("Meenakshi Enterprises", "Meenakshi Enterprises"),
    ("Raghav Auto Works", "Raghav Auto Works LLP"),
    ("Kaveri Textiles", "Kaveri Textiles Pvt Ltd"),
    ("Anand Electricals", "Anand Electricals"),
    ("Vishwas Logistics", "Vishwas Logistics Pvt Ltd"),
    ("Priya Steel Corp", "Priya Steel Corporation"),
    ("Nandini Foods", "Nandini Foods Pvt Ltd"),
)
_BANKS = (
    ("HDFC Bank", "HDFC0001234"),
    ("ICICI Bank", "ICIC0004567"),
    ("Axis Bank", "UTIB0000789"),
    ("State Bank of India", "SBIN0011223"),
    ("Kotak Mahindra Bank", "KKBK0003456"),
)
_PAYERS = (
    "Orbit Retail Pvt Ltd",
    "Bluepine Commerce Pvt Ltd",
    "Havelock Industries Pvt Ltd",
    "Sierra Wholesale Pvt Ltd",
)


@dataclass
class PayoutAdvice:
    """The facts printed on one advice.

    Every field here is something a fraudster has a motive to change, which is
    why they are data rather than literals: the benchmark tampers with them by
    re-rendering, so a forged advice differs from its genuine twin in exactly
    one field and nothing else.
    """

    payout_id: str
    utr: str
    amount_paise: int
    mode: str
    beneficiary: str
    beneficiary_legal: str
    account_last4: str
    ifsc: str
    bank: str
    payer: str
    narration: str
    created: datetime
    status: str = "Processed"

    @property
    def amount_text(self) -> str:
        return f"{self.amount_paise / 100:,.2f}"

    @property
    def value_date(self) -> str:
        return self.created.strftime("%d %b %Y, %I:%M %p")

    def replace(self, **changes) -> "PayoutAdvice":
        return field_replace(self, **changes)


def field_replace(advice: PayoutAdvice, **changes) -> PayoutAdvice:
    from dataclasses import replace as _replace

    return _replace(advice, **changes)


def sample_advice(rng: random.Random | None = None) -> PayoutAdvice:
    """One plausible advice. Deterministic when handed a seeded Random."""
    rng = rng or random.Random()
    beneficiary, legal = rng.choice(_BENEFICIARIES)
    bank, ifsc = rng.choice(_BANKS)
    mode = rng.choice(MODES)

    # RTGS has a 2 lakh floor in India, so amounts are drawn per mode. A
    # benchmark full of RTGS advices for 8,000 rupees would be a giveaway that
    # the fixtures were synthetic.
    if mode == "RTGS":
        rupees = rng.randrange(200_000, 4_000_000)
    elif mode == "NEFT":
        rupees = rng.randrange(5_000, 900_000)
    else:
        rupees = rng.randrange(1_000, 200_000)

    return PayoutAdvice(
        payout_id="pout_" + "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", k=14)),
        utr=("N" if mode == "NEFT" else "R" if mode == "RTGS" else "I")
        + "".join(rng.choices("0123456789", k=15)),
        amount_paise=rupees * 100 + rng.choice((0, 0, 0, 50)),
        mode=mode,
        beneficiary=beneficiary,
        beneficiary_legal=legal,
        account_last4="".join(rng.choices("0123456789", k=4)),
        ifsc=ifsc,
        bank=bank,
        payer=rng.choice(_PAYERS),
        narration=rng.choice(
            ("Vendor settlement", "Invoice payment", "Supplier payout", "Purchase order")
        )
        + " "
        + str(rng.randrange(1000, 9999)),
        created=datetime(2026, 8, 1) + timedelta(minutes=rng.randrange(0, 44_000)),
    )


def _texture(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    """A faint guilloche wash across the page.

    Two reasons, and the second is the one that matters. Real financial
    stationery carries a background pattern, so it reads correctly. But the
    signature is embedded in mid-frequency DCT coefficients of 8x8 blocks, and
    a flat white block has nothing to modulate — an advice is mostly empty
    paper, which is the documented failure case for this engine ("very blank
    images: too few textured blocks"). The wash gives the carrier something to
    hold onto in the margins.
    """
    for i in range(-HEIGHT, WIDTH + HEIGHT, 11):
        shade = 250 - (i % 3)
        draw.line([(i, 0), (i - HEIGHT, HEIGHT)], fill=(shade, shade, shade + 1), width=1)
    for _ in range(1400):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        draw.point((x, y), fill=(247, 249, 252))


def field_text(advice: PayoutAdvice, spec: Field) -> str:
    """The exact string printed in one field.

    Also the authoritative value the verifier compares a read against, which
    is why it is a function of the record rather than something the renderer
    formats inline: the two must agree character for character, and the only
    way to guarantee that is for there to be one of them.
    """
    if spec.name == "table_amount":
        return f"Rs {advice.amount_text}"
    if spec.name == "account":
        return f"XXXXXXXX{advice.account_last4}"
    if spec.attr is None:  # pragma: no cover - every other field has one
        return ""
    text = str(getattr(advice, spec.attr))
    return text.upper() if spec.upper else text


def _draw_text_tracked(draw, origin, text, face, fill, tracking: int) -> None:
    """Draw text, optionally with extra space between characters.

    One implementation, used by both the hero amount and the table rows,
    because the reader segments them the same way and a spacing difference
    between the two would show up as a forged amount on a genuine advice.
    """
    if not tracking:
        draw.text(origin, text, font=face, fill=fill)
        return
    x, y = origin
    x = float(x)
    for char in text:
        draw.text((x, y), char, font=face, fill=fill)
        x += draw.textlength(char, font=face) + tracking


def _draw_field(draw: ImageDraw.ImageDraw, spec: Field, value: str) -> None:
    """Draw one row exactly where layout.py says it goes.

    Vertical centring is computed from the spec's own height and point size so
    the glyphs land inside the rectangle the reader will sample. Drawing at a
    fixed offset was fine while every row was 52px at 21pt; it stops being
    fine the moment critical rows are taller and larger.
    """
    if spec.shaded:
        draw.rectangle([LEFT, spec.top, WIDTH - LEFT, spec.top + spec.height], fill=BAND)
    label_y = spec.top + (spec.height - 19) // 2
    draw.text((84, label_y), spec.label, font=font(19), fill=MUTED)
    value_y = spec.top + (spec.height - spec.size) // 2 - 2
    face = font(spec.size, bold=spec.bold, mono=spec.mono)
    _draw_text_tracked(draw, (VALUE_X, value_y), value, face, INK, spec.tracking)


def render(advice: PayoutAdvice, output: str | Path, *, seed: int = 0) -> Path:
    """Draw one advice to a PNG and return the path."""
    rng = random.Random(seed)
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    _texture(draw, rng)

    # ---- header band -------------------------------------------------
    draw.rectangle([0, 0, WIDTH, 132], fill=NAVY)
    draw.text((64, 40), "Razorpay", font=font(34, bold=True), fill=(255, 255, 255))
    wordmark_w = draw.textlength("Razorpay", font=font(34, bold=True))
    draw.text((64 + wordmark_w, 40), "X", font=font(34, bold=True), fill=BLUE)
    draw.text((64, 82), "Business Banking", font=font(17), fill=(150, 175, 210))
    title = "PAYOUT ADVICE"
    tw = draw.textlength(title, font=font(22, bold=True))
    draw.text((WIDTH - 64 - tw, 52), title, font=font(22, bold=True), fill=(255, 255, 255))
    draw.rectangle([0, 132, WIDTH, 137], fill=BLUE)

    # ---- specimen marking --------------------------------------------
    # Drawn here, before anything is signed, so no code path produces an
    # unmarked advice.
    _specimen(draw)

    # ---- status + amount ---------------------------------------------
    y = 190
    pill_w = int(draw.textlength(advice.status.upper(), font=font(18, bold=True))) + 44
    draw.rounded_rectangle([64, y, 64 + pill_w, y + 40], radius=20, fill=GREEN_WASH)
    draw.text((86, y + 10), advice.status.upper(), font=font(18, bold=True), fill=GREEN)

    draw.text((64, y + 68), "Amount transferred", font=font(19), fill=MUTED)
    _draw_text_tracked(draw, (64, y + 100), f"Rs {advice.amount_text}",
                       font(52, bold=True), INK, HERO_AMOUNT.tracking)
    draw.text(
        (64, y + 168),
        f"by {advice.mode} to {advice.beneficiary_legal}",
        font=font(20),
        fill=MUTED,
    )

    # ---- section headings, then every field from the spec -------------
    for heading, top in SECTIONS:
        draw.text((LEFT, top), heading, font=font(17, bold=True), fill=MUTED)
        draw.line([(LEFT, top + 34), (WIDTH - LEFT, top + 34)], fill=RULE, width=2)

    for spec in FIELDS:
        if spec.name == "hero_amount":
            continue  # drawn above, in the summary block
        _draw_field(draw, spec, field_text(advice, spec))

    # ---- footer ------------------------------------------------------
    fy = 1280
    draw.line([(64, fy), (WIDTH - 64, fy)], fill=RULE, width=2)
    draw.text(
        (64, fy + 22),
        "This advice confirms the transfer was submitted to the beneficiary bank.",
        font=font(18),
        fill=MUTED,
    )
    draw.text(
        (64, fy + 50),
        "NEFT and RTGS settle in batches; credit may reflect after this advice is issued.",
        font=font(18),
        fill=MUTED,
    )
    draw.text(
        (64, fy + 90),
        "Carries an embedded Trust Shield signature. Verify before releasing goods.",
        font=font(18, bold=True),
        fill=NAVY,
    )

    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination


def _specimen(draw: ImageDraw.ImageDraw) -> None:
    """Mark the page as a test fixture, legibly and permanently."""
    draw.rectangle([0, 137, WIDTH, 176], fill=(255, 244, 219))
    text = "SPECIMEN - synthetic fixture generated for fraud-detection testing"
    tw = draw.textlength(text, font=font(17, bold=True))
    draw.text(((WIDTH - tw) / 2, 147), text, font=font(17, bold=True), fill=(146, 94, 8))
