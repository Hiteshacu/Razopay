"""A RazorpayX Payroll payslip, and the layout both sides agree on.

Why a payslip and not another advice. A payout advice is checked by somebody
who was sent it; a payslip is checked by somebody the employee is asking for
something — a lender, a landlord, an employer running a background check. That
party has no channel to the payroll system at all. Account Aggregator cannot
carry it: its data providers are regulated financial institutions, and a
private employer is not one, so an employer-issued payslip cannot travel that
route even in principle. DigiLocker holds government documents. What is left
is a PDF, a phone call, and an industry of background-verification firms whose
existence is the measure of the gap.

So a payslip that proves itself is worth more than an advice that does, and it
is the same machinery: RazorpayX Payroll prints these, which means it can sign
them as it prints them.

The layout repeats what layout.py learned rather than rediscovering it.

Size is a security property. The glyph reader is exact at 52pt and confused
217 for 227 at 21pt once a document had been compressed, so every field a
verdict rests on is printed large. RazorpayX renders these itself, so
legibility under compression is a decision available to be made.

The alphabet is a security property. A field that can only contain digits
should not let the reader consider an I, because that only creates the chance
to confuse it with a 1. Every field declares the smallest set that can appear
in it.

Names are printed in capitals with tracking. Mixed case at 30pt put ascenders
and descenders against each other and the segmenter merged them; two glyphs
sharing a pixel are one connected component, and "SUNDAR TRADERS" came back
"SUNDAR TDERS". Tracking guarantees a gap.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from .advice import BAND, BLUE, INK, NAVY, PAPER, _draw_text_tracked, _texture
from .fonts import font
from .layout import DIGITS, MONEY, NAME, UPPER, Field

WIDTH, HEIGHT = 1000, 1400

#: Left edge of the value column, matching the advice so one reader serves both.
VALUE_X = 430
RIGHT = 936
LEFT = 64


@dataclass(frozen=True)
class Payslip:
    """The facts printed on one payslip.

    Data rather than literals for the same reason the advice is: the benchmark
    forges one by re-rendering with a single field changed, so a forgery
    differs from its genuine twin in exactly that field and nothing else.
    """

    slip_id: str
    employee: str
    employee_id: str
    designation: str
    period: str
    pan: str
    uan: str
    employer: str
    basic_paise: int
    hra_paise: int
    allowance_paise: int
    pf_paise: int
    tax_paise: int
    paid_on: datetime

    @property
    def gross_paise(self) -> int:
        return self.basic_paise + self.hra_paise + self.allowance_paise

    @property
    def deductions_paise(self) -> int:
        return self.pf_paise + self.tax_paise

    @property
    def net_paise(self) -> int:
        return self.gross_paise - self.deductions_paise

    def _money(self, paise: int) -> str:
        return f"{paise / 100:,.2f}"

    @property
    def net_text(self) -> str:
        return self._money(self.net_paise)

    @property
    def gross_text(self) -> str:
        return self._money(self.gross_paise)

    @property
    def basic_text(self) -> str:
        return self._money(self.basic_paise)

    @property
    def deductions_text(self) -> str:
        return self._money(self.deductions_paise)

    @property
    def paid_on_text(self) -> str:
        return self.paid_on.strftime("%d %b %Y")

    def replace(self, **changes) -> "Payslip":
        from dataclasses import replace as _replace

        return _replace(self, **changes)


#: The hero. A forger changes net pay first, because it is the number a lender
#: multiplies to decide what someone can borrow. Printed at 52pt for the same
#: reason the advice prints its amount there: it is the field held to account.
NET_PAY = Field(
    name="net_pay", label="", attr="net_text",
    top=300, height=83, size=52, bold=True,
    alphabet=MONEY + "Rs", critical=True, tracking=2, numeric=True, hero=True,
)

FIELDS: tuple[Field, ...] = (
    NET_PAY,
    # Caps and tracked, read against a caps-only alphabet. The name is what
    # ties the document to the person presenting it, so it is adjudicated.
    Field("employee", "Employee", "employee", 470, 62, 30, bold=True,
          alphabet=UPPER + " .&-", critical=True, shaded=True, upper=True,
          tracking=3),
    Field("employee_id", "Employee ID", "employee_id", 532, 62, 30, mono=True,
          alphabet=UPPER + DIGITS + "-", critical=True, shaded=True, tracking=2),
    Field("designation", "Designation", "designation", 594, 56, 21,
          alphabet=NAME, readable=False),
    Field("period", "Pay period", "period", 650, 62, 30, bold=True,
          alphabet=UPPER + DIGITS + " ", critical=True, shaded=True,
          upper=True, tracking=2),
    # Earnings and deductions. Gross is adjudicated because a forger who
    # raises net and leaves gross alone is caught by arithmetic a human does.
    Field("basic", "Basic", "basic_text", 780, 56, 21,
          alphabet=MONEY + "Rs", readable=False),
    Field("gross", "Gross earnings", "gross_text", 836, 62, 30, bold=True,
          alphabet=MONEY + "Rs", critical=True, shaded=True, tracking=2,
          numeric=True),
    Field("deductions", "Total deductions", "deductions_text", 898, 62, 30,
          bold=True, alphabet=MONEY + "Rs", critical=True, shaded=True,
          tracking=2, numeric=True),
    Field("pan", "PAN", "pan", 1020, 56, 21, mono=True,
          alphabet=UPPER + DIGITS, readable=False),
    Field("uan", "UAN", "uan", 1076, 56, 21, mono=True,
          alphabet=DIGITS, readable=False),
    Field("paid_on", "Credited on", "paid_on_text", 1132, 56, 21,
          alphabet=NAME + DIGITS, readable=False),
    Field("employer", "Employer", "employer", 1252, 56, 21, alphabet=NAME,
          readable=False),
)

SECTIONS: tuple[tuple[str, int], ...] = (
    ("EMPLOYEE", 426),
    ("EARNINGS AND DEDUCTIONS", 736),
    ("STATUTORY", 976),
    ("EMPLOYER", 1208),
)

BY_NAME = {f.name: f for f in FIELDS}

#: The fields a verdict may rest on: identity, period and money, each measured
#: readable. Everything else is printed and shown but never adjudicated.
CHECKED = tuple(f for f in FIELDS if f.critical and f.readable)

_FIRST = ("Ramesh", "Priya", "Anand", "Kavya", "Imran", "Sunita", "Vikram", "Meera")
_LAST = ("Kulkarni", "Sharma", "Iyer", "Nair", "Bose", "Reddy", "Menon", "Shah")
_ROLE = ("Senior Engineer", "Operations Lead", "Account Manager",
         "Finance Analyst", "Design Lead", "Support Specialist")
_EMPLOYER = ("Orbit Retail Pvt Ltd", "Lumen Systems Pvt Ltd",
             "Cardamom Foods Pvt Ltd", "Northwind Logistics Pvt Ltd")


def field_text(slip: Payslip, spec: Field) -> str:
    """Exactly the string that is printed for one field."""
    if spec.attr is None:
        return ""
    value = str(getattr(slip, spec.attr))
    if spec.alphabet is MONEY or "Rs" in spec.alphabet:
        value = f"Rs {value}"
    return value.upper() if spec.upper else value


def sample_payslip(rng: random.Random | None = None) -> Payslip:
    """One plausible payslip. Deterministic when handed a seeded Random."""
    rng = rng or random.Random()
    basic = rng.randrange(30_000, 90_000) * 100
    paid = datetime(2026, rng.randrange(1, 9), rng.randrange(1, 28), 11, 30)
    return Payslip(
        slip_id="slip_" + "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(14)),
        employee=f"{rng.choice(_FIRST)} {rng.choice(_LAST)}",
        employee_id="EMP-" + str(rng.randrange(10_000, 99_999)),
        designation=rng.choice(_ROLE),
        period=(paid - timedelta(days=20)).strftime("%B %Y"),
        pan="".join(rng.choice(UPPER) for _ in range(5))
            + str(rng.randrange(1000, 9999)) + rng.choice(UPPER),
        uan=str(rng.randrange(10**11, 10**12 - 1)),
        employer=rng.choice(_EMPLOYER),
        basic_paise=basic,
        hra_paise=int(basic * 0.40),
        allowance_paise=int(basic * 0.15),
        pf_paise=int(basic * 0.12),
        tax_paise=int(basic * 0.08),
        paid_on=paid,
    )


def _draw_field(draw: ImageDraw.ImageDraw, spec: Field, value: str) -> None:
    """One labelled row: the shaded band, the label, then the value."""
    left, top, right, bottom = spec.box
    if spec.shaded:
        draw.rectangle([LEFT, top - 6, RIGHT, bottom + 2], fill=BAND)
    draw.text((LEFT, top + (spec.height - 21) // 2), spec.label,
              font=font(17), fill=(110, 125, 150))
    face = font(spec.size, bold=spec.bold, mono=spec.mono)
    origin = (left, top + (spec.height - spec.size) // 2 - 2)
    if spec.tracking:
        _draw_text_tracked(draw, origin, value, face, INK, spec.tracking)
    else:
        draw.text(origin, value, font=face, fill=INK)


def render(slip: Payslip, output: str | Path, *, seed: int = 0) -> Path:
    """Draw one payslip to a PNG and return the path.

    Stamped SPECIMEN before it is signed, so every forgery the benchmark makes
    lands on a page that already says what it is. A demo that produces
    documents indistinguishable from real payroll output is a demo that
    produces usable forgeries.
    """
    rng = random.Random(seed)
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    _texture(draw, rng)

    # ---- header ------------------------------------------------------
    draw.rectangle([0, 0, WIDTH, 132], fill=NAVY)
    draw.text((64, 40), "Razorpay", font=font(34, bold=True), fill=(255, 255, 255))
    mark = draw.textlength("Razorpay", font=font(34, bold=True))
    draw.text((64 + mark, 40), "X", font=font(34, bold=True), fill=BLUE)
    draw.text((64, 82), "Payroll", font=font(17), fill=(150, 175, 210))
    title = "PAYSLIP"
    tw = draw.textlength(title, font=font(22, bold=True))
    draw.text((WIDTH - 64 - tw, 52), title, font=font(22, bold=True), fill=(255, 255, 255))
    draw.rectangle([0, 132, WIDTH, 137], fill=BLUE)

    # ---- hero: net pay ------------------------------------------------
    draw.text((64, 196), "NET PAY CREDITED", font=font(19, bold=True),
              fill=(110, 125, 150))
    draw.text((64, 232), f"Pay period {slip.period}", font=font(19),
              fill=(110, 125, 150))
    _draw_field(draw, NET_PAY, field_text(slip, NET_PAY))

    # ---- sections and rows --------------------------------------------
    for heading, y in SECTIONS:
        draw.text((64, y), heading, font=font(17, bold=True), fill=BLUE)
        draw.line([(64, y + 34), (RIGHT, y + 34)], fill=(214, 224, 238), width=2)

    for spec in FIELDS:
        if spec is NET_PAY:
            continue
        _draw_field(draw, spec, field_text(slip, spec))

    # ---- footer -------------------------------------------------------
    draw.text((64, 1330),
              f"Slip {slip.slip_id} - system generated, signed by RazorpayX Payroll",
              font=font(15), fill=(140, 155, 178))

    _specimen(draw)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out


def _specimen(draw: ImageDraw.ImageDraw) -> None:
    """Mark the page, before anything signs it."""
    face = font(19, bold=True)
    text = "SPECIMEN - GENERATED FOR DEMONSTRATION"
    tw = draw.textlength(text, font=face)
    draw.text(((WIDTH - tw) / 2, 1290), text, font=face, fill=(196, 208, 224))
