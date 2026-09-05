# PayProof

**Tamper detection for RazorpayX payout advices and payslips.**
The document proves itself — no database, no lookup, no account.

| | |
|---|---|
| **Live portal** | https://razopay-admin.onrender.com |
| **Live API** | https://p01--razopay-api--fbm4b6hyrltk.code.run/docs |
| **Demo login** | `default@gmail.com` / `PayProofDemo2026!` |
| **Track** | Track 2 — AI Risk Manager |

Try it without signing in: open the portal, click **Verify any document**, switch on
**RazorpayX payout advice**, and upload a signed advice. Edit the amount in any image
editor first and it comes back `ALTERED`, with the changed region boxed on the page.

---

## The problem

Razorpay has a name for it. In their own 2026 settlement playbook they call the window
between a payment being made and the money being visible the **"opacity zone"** —
merchants know the customer paid and money eventually arrives, but visibility breaks
down.

NEFT and RTGS settle in batches. So a vendor holding a payout advice cannot confirm it:
their bank shows nothing, because the credit genuinely has not arrived yet.

Fraudsters work in exactly that window.

- A Mumbai used-car dealer lost **₹6.5 lakh** to an edited transfer slip printed on paper.
- Ranka Jewellers lost **₹3.48 lakh of gold** to a fabricated NEFT confirmation on a phone.

Both were holding a document that looked exactly like a real one.

Every defence available today says *look somewhere else* — check your bank, wait for the
SMS, match the UTR. During the opacity zone there is nothing to look at. A soundbox
announces UPI credits; these are not UPI.

## The approach

RazorpayX signs an advice **as it prints it**. The signature is not attached as metadata —
an RSA-PSS signature and a perceptual fingerprint are spread across every 8×8 DCT block of
the image, so the proof survives a screenshot and a trip through a messaging app.

Anyone holding that page checks it in a browser and gets one of three answers:

| Verdict | Meaning |
|---|---|
| `GENUINE` | RazorpayX issued this, and the proof is intact everywhere |
| `ALTERED` | RazorpayX issued it, then part of it was changed — shown boxed on the page |
| `NOT_ISSUED` | No embedded proof, or damaged past recovery |

**Verification reads nothing but the file.** No database, no reference copy, no id to
type. A document issued a year ago verifies exactly as well as one issued a minute ago,
and Razorpay does not have to be online for a vendor to get an answer.

## How tamper detection works

The interesting part, because the two obvious approaches do not work.

**The whole-page fingerprint cannot catch small edits.** The tolerance that lets it
survive WhatsApp is the same tolerance that absorbs a repainted figure. Measured: the
identical 4.1% edit passed on one advice and was caught on another. It let **11 of 16
edits through**.

**A finer fingerprint does not help either.** A grid of regional hashes, tried at four
grid sizes, caught **0 of 30** — each cell is still a downsample, so a changed digit gets
averaged away.

The signal is the carrier itself. The embedded signature lives in thousands of 8×8 blocks,
each holding one bit of a payload that survives locally destroyed blocks because it is
repeated across the page and majority-voted. So the payload is recovered **from the edited
page**, and every block is asked whether it still carries it.

Measuring *how much* damage fails: a photo of a screen concentrates damage 22× above its
own mean, the weakest forgery only 13×. And measuring *which bits read back wrong* only
half works — it catches an edit that covers a whole field and misses a single digit,
because painting over a value leaves a flat block whose two mid-frequency coefficients are
both near zero, so which one is larger becomes a coin toss. Half the blocks inside an
erased digit still read back correctly, and the patch dissolves into speckle.

What separates them is the **margin**: how far each block's coefficient pair still leans
the way the payload says it should. Signing pushes every pair apart by at least 36 DCT
units. Nothing enforces that on pixels a forger paints, so the margin collapses across
every block they touched — erased or retyped, it makes no difference — while honest
recompression only thins it. Judged against the page's *own* median margin, so a dimmed,
brightened or heavily recompressed copy is compared with itself rather than with an
absolute number.

## Measured results

Held-out evaluation split (seed 5000); thresholds were fixed on a development split
(seed 1000) and never refitted.

**Carrier tamper detection**, over 72 honest copies and 104 edits the carrier could be
read from:

| | Sign disagreement | Margin collapse |
|---|---|---|
| False accusations | 0 | **0** |
| Missed edits | 52 of 104 | **8 of 104** |
| Honest patch sizes | 0–6 | 0–8 |
| Edited patch sizes | 0–27 | 10–629 |
| Threshold | 7 | **9** |

The 52 misses were all small edits — one digit erased or swapped — which is the case a
forger actually needs. The 8 that remain are one narrow case: a single digit in the small
secondary amount row, replaced by a same-width glyph. Every edit to the headline amount is
caught at every size tested.

**Region localisation** — 1 edit gives 1 box, 2 give 2, 3 give 3, each on the field that
was actually repainted.

**Payout advice benchmark** (`python -m razorpayx.cli benchmark --advices 8 --seed 5000`)

```
Forgeries rejected     152 / 152     recall     1.000
Falsely accused          0 / 80      precision  1.000
Genuine passed          72 / 80      FPR        0.000
```

**Payslips** — the same detector, unchanged: genuine slips pass, and erasing one digit of
net pay is caught and boxed.

## What it cannot do

Stated because a detector's limits matter as much as its numbers.

**A photograph of a screen fails at every embedding strength tested.** That is geometry,
not signal — rescreening and perspective move the 8×8 grid the carrier is read from, and
no amount of amplitude repairs a grid that has moved. This is the remaining 4 of 40 in the
benchmark above.

**On a heavy downscale or a messaging-app re-encode the carrier cannot be read back
directly**, and the detector returns `cannot measure` rather than `clean`. A detector that
reports "I could not look" as "nothing is wrong" is worse than one that declines to
answer.

## Where to look in the code

| Path | What it is |
|---|---|
| `razorpayx/locate.py` | Tamper detection and region localisation. Every measurement is recorded in the comments, including the threshold study. |
| `razorpayx/benchmark.py` | The held-out evaluation. |
| `utils.py` | The signing engine — DCT embedding, fingerprint, key handling. |
| `verify_poster.py` | Verification and its recovery tiers. |
| `razorpayx/advice.py`, `payslip.py` | Document renderers and their field layouts. |
| `backend/app/routes/` | FastAPI: issue, verify, accounts, audit. |
| `admin-portal/src/pages/Verify.tsx` | The public verifier. |

## Running it

**Requirements:** Python 3.11, Node 20.

```bash
# API
cd backend
python -m venv .venv && .venv/Scripts/activate    # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env                               # then fill it in
python -m uvicorn app.main:app --reload --port 8000

# Portal
cd admin-portal
npm ci
npm run dev                                        # http://localhost:5173
```

`backend/.env.example` documents every variable, including why
`REQUIRE_ADMIN_AUTH` must be `true` on anything reachable from the internet.

**Run the benchmark yourself:**

```bash
python -m razorpayx.cli benchmark --advices 8 --seed 5000 --detail
```

## Architecture

```
Issue                                    Verify
─────                                    ──────
render the document                      recover the payload from the file
        ↓                                        ↓
fingerprint it (128-bit perceptual)      check the RSA signature
        ↓                                        ↓
sign with RSA-PSS                        compare the fingerprint
        ↓                                        ↓
weave signature + fingerprint            ask every 8×8 block how hard it
across every 8×8 DCT block               still leans the way it was written
        ↓                                        ↓
                                          largest flattened patch → edited, and where
store in S3, record in Firestore
```

Signing runs in one batched matrix product rather than ~25,000 per-block DCT calls —
4.7× faster, verified against the previous output.

## Stack

FastAPI · Firebase Auth + Firestore · Backblaze B2 (S3) · React 19 + Vite + TypeScript ·
OpenCV + NumPy · `cryptography` (RSA-PSS over SHA-256)

Backend on Northflank, portal on Render, both always-on.
