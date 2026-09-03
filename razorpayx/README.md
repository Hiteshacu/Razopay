# Payout advice forgery detection

**Track 02 — AI Risk Manager.** One class of loss: forged RazorpayX payout
advices used to obtain goods before a transfer settles.

## The loss

RazorpayX sends money by UPI, IMPS, NEFT and RTGS, and issues the payer a
payout advice they forward to the beneficiary as proof. NEFT and RTGS settle
in batches — minutes to hours. So a vendor asked to release goods against an
advice is in a window where the money legitimately has not arrived and
checking their own bank proves nothing. A soundbox does not help either; it
announces UPI credits, and these are not UPI.

Documented losses of exactly this shape:

- Mumbai used-car dealer, **₹6.5 lakh**, against an edited NEFT slip printed on paper
- Ranka Jewellers, **₹3.48 lakh** of gold, against a fabricated NEFT confirmation
- Satara jewellers and phone shops, **₹5.23 lakh** across several shops
- An organised ring in Sant Ravidas Nagar working gold traders the same way

## What was built

RazorpayX signs the advice as it issues it; anyone holding one can check it,
with no account.

Two independent checks, because neither catches both frauds:

| | Catches | Blind to |
|---|---|---|
| **Embedded signature** (existing Trust Shield engine) | wholesale fabrication; survives screenshots | small edits — its page fingerprint tolerates them |
| **Field read** (this package) | a repainted amount, UTR, beneficiary or account | an image that was never signed |

## The measurement that shaped the design

A repainted amount — ₹29,30,217 to ₹99,30,217, **1.98% of the page** — was put
through three detectors before the fourth worked.

| Approach | Result |
|---|---|
| Whole-page perceptual fingerprint | **AUTHENTIC.** The edit sits inside the tolerance that lets a signature survive recompression. |
| Per-zone perceptual hashing | **Overlap.** JPEG q95 moved the amount field's hash 41 bits; the forgery moved it 30. |
| Per-zone pixel differencing | **Overlap.** On a WhatsApp copy, compression noise measured 0.069 across all zones; the forgery contributed 0.047. |
| **Reading the printed characters** | **Works.** Compression destroys glyph *appearance*, not glyph *identity*. |

Robustness to compression and blindness to small edits are the same property.
You cannot fix that by comparing pixels harder — you have to read the text.

The reader is a glyph matcher, not an OCR model. RazorpayX renders these
advices itself, so the typeface, point size and position of every field are
known before a document is read. That makes it "which of these known glyphs is
this", which template matching answers deterministically in a few megabytes —
and fits the 256 MB container the free tier allows, where torch does not.

## Held-out results

Evaluation split seed 5000; the reader's alphabets and thresholds were fixed on
the 1000-series and never refitted. 10 advices → 100 genuine copies, 190
forgeries.

```
FORGERIES
  rejected (vendor warned)    190 / 190
    - named as edited         154      correct attribution
    - named as unsigned        36      right call, wrong reason
  WAVED THROUGH                 0      <- the dangerous failure

COST OF BEING WRONG
  genuine passed               90 / 100
  genuine FALSELY ACCUSED       0      <- the expensive one
  genuine signature lost       10      photo-of-screen, see below

Precision            1.000
Recall               1.000
Attribution rate     0.811
False-positive rate  0.000
```

The hardest case works: **a single changed digit** (₹8,03,626 → ₹8,03,826),
then sent through WhatsApp, was caught 10/10 in every journey.

### What it does not do

- **A photo of a screen fails.** Rotation and camera softness break watermark
  recovery, so all 10 came back "no signature found". Wrong, but it fails
  *safe* — it refuses rather than passing a fake. A vendor must send the file
  or a screenshot, not a photograph of a monitor.
- **Attribution is 81%, not 100%.** The other 19% are rejected as "never
  issued" rather than "edited", because repainting a 62px band destroys the
  carrier blocks under it and the payload cannot be recovered at all. The
  vendor is told not to release goods either way; the explanation is wrong.
- **Fields are only checked where they can be read.** Fields printed at 21pt
  were measured unreliable after compression and are rendered but not
  adjudicated. `layout.py` records which are which.

## Defence only

There is no `forge` command and no endpoint that produces a forged advice.
Forgeries are built in-process by `benchmark.py` to measure recall and are
never written to a public path. Every generated advice is stamped **SPECIMEN**
in the pixels before it is signed, so no code path emits a clean unmarked
RazorpayX advice.

## Running it

```bash
python -m razorpayx.cli issue --seed 42
python -m razorpayx.cli verify <image.png> --record <record.json> --public-key <pub.pem>
python -m razorpayx.cli benchmark --advices 10 --detail
```

The web demo is at `/api/payout-advice/*` and the **Payout advice** page in the
portal: issue a signed advice, download it, edit the amount in any image
editor, and upload it back.

## Layout

| File | |
|---|---|
| `layout.py` | one spec for every field — position, size, alphabet. Renderer and reader both derive from it so they cannot drift. |
| `advice.py` | renders an advice; stamps SPECIMEN before signing |
| `issue.py` | render → sign → record what was printed |
| `read.py` | the glyph matcher |
| `check.py` | signature + field comparison → verdict |
| `adversary.py` | forgeries and honest journeys; benchmark only |
| `benchmark.py` | held-out measurement |
