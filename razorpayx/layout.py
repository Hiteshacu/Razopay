"""One description of the advice, used by both the renderer and the reader.

The renderer and the reader must agree about where every field sits, what
size it is printed at, and which characters can legally appear in it. Holding
that in two places guarantees they drift, and the failure is silent: the
reader quietly starts sampling the wrong rectangle and reports a mismatch on
a genuine document. So the layout lives here once, and both sides derive from
it.

Two things were learned by measuring and are encoded here rather than
written down somewhere and forgotten.

Size is a security property. The glyph reader is exact at 52pt across every
transform tested, including a 960px WhatsApp re-encode at quality 46. At 21pt
the same reader confused 217 for 227 and 0 for 8 once the document had been
compressed. A field nobody can read reliably cannot be verified reliably, so
fields worth checking are printed large. RazorpayX renders these advices
itself, which means legibility under compression is a design decision that is
available to be made, not a constraint to be suffered.

The alphabet is a security property too. A UTR is one letter and fifteen
digits, so allowing the reader to consider 'I' as a candidate only lets it
confuse a 1 for an I. Every field declares the smallest character set that can
appear in it, which removes whole classes of confusion before they happen.
"""

from __future__ import annotations

from dataclasses import dataclass

CANON_W, CANON_H = 1000, 1400

DIGITS = "0123456789"
MONEY = "0123456789,."
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
NAME = UPPER + "abcdefghijklmnopqrstuvwxyz .&-"

# Left edge of the value column, and the right margin.
VALUE_X = 430
RIGHT = 936
LEFT = 64


@dataclass(frozen=True)
class Field:
    """One printed value on the advice."""

    name: str
    label: str
    #: Attribute on PayoutAdvice, or None when the renderer supplies the text.
    attr: str | None
    top: int
    height: int
    size: int
    bold: bool = False
    mono: bool = False
    alphabet: str = NAME
    #: Whether changing this field is how the money gets stolen.
    critical: bool = False
    #: Whether the reader is trusted on this field. Set from measurement.
    readable: bool = True
    #: Pixels to skip at the left of the value, to step over a fixed prefix
    #: such as "Rs " that the reader would otherwise try to interpret.
    value_offset: int = 0
    shaded: bool = False
    #: Print (and compare) this field in capitals.
    upper: bool = False
    #: Compare this field on its digits alone.
    #:
    #: Explicit rather than inferred from the alphabet. It used to be decided
    #: by testing `alphabet is MONEY`, which silently stopped being true the
    #: moment "Rs" was added to the alphabet so the prefix could be read and
    #: discarded — every genuine advice was then called a forgery because the
    #: expected value kept no letters and the read one did.
    numeric: bool = False
    #: Extra pixels between characters when drawing.
    #:
    #: Bold caps at 30pt kern tightly enough that "RA" touches, and two glyphs
    #: sharing a pixel are one connected component - the segmenter returned a
    #: single blob and the matcher scored it as one letter, so SUNDAR TRADERS
    #: read as SUNDAR TDERS. Tracking guarantees a gap. A document meant to be
    #: machine-checked can afford to be set for legibility.
    tracking: int = 0
    #: The one field printed across the page rather than in the value column.
    #:
    #: A flag rather than a name comparison. This used to test for the literal
    #: "hero_amount", which silently gave the payslip's net pay the narrow
    #: column geometry and cropped it — a layout deciding where to sample by
    #: recognising one document's field name cannot be reused by a second.
    hero: bool = False

    @property
    def box(self) -> tuple[int, int, int, int]:
        """The rectangle the reader samples, in canonical coordinates."""
        left = (LEFT if self.hero else VALUE_X) + self.value_offset
        return (left, self.top, 760 if self.hero else RIGHT,
                self.top + self.height)


# The hero amount is printed at 52pt and is the field a forger changes first,
# so it is the one the reader is held to. "Rs " is stepped over: it is a fixed
# prefix, and letting the matcher guess at an R with a digit alphabet produced
# an unstable leading character that differed between an original and a
# rescaled copy — a false accusation waiting to happen.
# "Rs" is read and then discarded rather than cropped past. Cropping was set
# to 78px against a measured prefix width of 71px, so it cut 7px off the first
# digit — and a left-clipped 8 is a 3, which is how Rs 803,626 read as 303,626
# on a pristine file. Any fixed offset is a guess about font metrics that
# differ between platforms; reading the prefix and dropping it cannot misjudge.
HERO_AMOUNT = Field(
    name="hero_amount", label="", attr="amount_text",
    top=283, height=83, size=52, bold=True,
    alphabet=MONEY + "Rs", critical=True, tracking=2, numeric=True, hero=True,
)

# 30pt for everything security-critical, 21pt for context that nobody steals.
#
# The vertical budget is tight and hand-checked: every row's top is the
# previous row's top plus its height, and each section heading sits in a 20px
# gap above its rule. Getting this wrong does not raise — it silently draws a
# heading through a value, so the numbers below are laid out explicitly rather
# than accumulated by a running cursor.
FIELDS: tuple[Field, ...] = (
    HERO_AMOUNT,
    Field("payout_id", "Payout ID", "payout_id", 484, 56, 21, mono=True,
          alphabet=UPPER + DIGITS + "_", readable=False),
    # The leading N/R/I is read rather than cropped past. Cropping it meant
    # slicing 26px off the left of the field, which clipped the first digit
    # and turned every 7 into a 2 - on pristine files. The letter is in the
    # alphabet and normalisation drops it afterwards, which cannot mis-slice.
    Field("utr", "UTR / Reference", "utr", 540, 62, 30, mono=True,
          alphabet=DIGITS + "NRI", critical=True, shaded=True, numeric=True),
    Field("mode", "Transfer mode", "mode", 602, 56, 21, bold=True,
          alphabet=UPPER, readable=False),
    Field("value_date", "Value date", "value_date", 658, 56, 21,
          alphabet=NAME + DIGITS + ":", readable=False),
    # Tracking, for the same reason the beneficiary needs it: "244171500"
    # rendered its adjacent 4s touching, the segmenter returned one blob, and
    # the pair read as a single digit.
    Field("table_amount", "Amount", None, 714, 62, 30, bold=True,
          alphabet=MONEY + "Rs", critical=True, shaded=True, tracking=2,
          numeric=True),
    # Printed in caps, and read against a caps-only alphabet. Mixed case put
    # lowercase ascenders and descenders next to each other at 30pt, and the
    # segmenter merged "Pvt" into a single blob it scored as "-". Caps is also
    # what a bank advice actually looks like, so this costs nothing.
    Field("beneficiary", "Beneficiary", "beneficiary_legal", 840, 62, 30, bold=True,
          alphabet=UPPER + " .&-", critical=True, shaded=True, upper=True,
          tracking=3),
    Field("account", "Account number", None, 902, 62, 30, mono=True,
          alphabet="X" + DIGITS, critical=True, shaded=True, numeric=True),
    Field("ifsc", "IFSC", "ifsc", 964, 56, 21, mono=True,
          alphabet=UPPER + DIGITS, readable=False),
    Field("bank", "Bank", "bank", 1020, 56, 21, alphabet=NAME, readable=False),
    Field("narration", "Narration", "narration", 1076, 56, 21,
          alphabet=NAME + DIGITS, readable=False),
    Field("payer", "Debited from", "payer", 1196, 56, 21, alphabet=NAME,
          readable=False),
)

#: (heading text, y of the heading baseline). The rule is drawn 34px below.
SECTIONS: tuple[tuple[str, int], ...] = (
    ("TRANSFER DETAILS", 440),
    ("BENEFICIARY", 796),
    ("DEBITED FROM", 1152),
)

BY_NAME = {field.name: field for field in FIELDS}

#: The fields a verdict is allowed to rest on: money-critical and measured
#: readable. Everything else is rendered and shown, but not adjudicated.
CHECKED = tuple(f for f in FIELDS if f.critical and f.readable)
