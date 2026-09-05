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

One more thing decides whether that works, and it only shows up on real documents. The
payload is repeated at most eleven times however large the page is, so the share of blocks
carrying a bit at all falls as the page grows:

| Page | Blocks | Carry a bit |
|---|---|---|
| Payout advice, 1000×1400 | 21,875 | **93%** |
| Scanned letter, 1400×1750 | 38,150 | **65%** |
| Phone photo of one, 2000×2600 | 81,250 | **31%** |

A fixed window asking "are all four of my neighbours damaged?" reads every block carrying
nothing as a block that is fine. On a large page an edit therefore arrives as a sieve and
dissolves — 32 of 42 letter edits went through that way. So the window grows until it
expects to hold as many carriers as it held on the page the thresholds were measured on,
and only blocks carrying a bit are allowed to vote. What reconnects the pieces afterwards
stays fixed, because that is a reconnection and not a measurement.

## Measured results

Held-out evaluation split (seed 5000); thresholds were fixed on a development split
(seed 1000) and never refitted.

**Carrier tamper detection.** Two corpora, each split into a development set the
thresholds were fixed on and a held-out set they were never refitted against: payout
advices at 1000×1400, and scanned-letter pages at 1400×1750 through 2000×2500.

| Detector | False accusations | Missed edits |
|---|---|---|
| Margin collapse, fixed window | 0 of 198 | 61 of 232 |
| Margin collapse, window sized to carrier density | **0 of 198** | **27 of 232** |

(Sign disagreement, the detector before either of these, was measured on the advice corpus
only: 52 of 104 held-out edits missed against 8 for the margin map.)

Broken out, at threshold 9:

| Split | Fixed window | Density-sized |
|---|---|---|
| Advices, development | 5 of 65 missed | 5 of 65 |
| Advices, held out | 6 of 104 | 6 of 104 |
| Letters, development | 18 of 21 | **2 of 21** |
| Letters, held out | 32 of 42 | **14 of 42** |

Advices are untouched — on a dense page the sizing reduces to the window it replaced — and
the large pages, where the detector was effectively blind, improve by more than half.

Honest journeys across all four splits reach 8 at the very worst, a sharpened copy, so
nine is the lowest threshold that accuses nobody. Eight was measured too: it buys ten
edits and costs one false accusation, and was not taken.

What still gets through is small and specific: a single digit replaced by a same-width
glyph, and two-character edits on the largest pages. Redrawn text restores the contrast the
margin is read from, so those blocks go back to a coin toss.

**These numbers have real spread in them, and it is worth stating plainly.** RSA-PSS salts
every signature, so signing the same page twice puts a different set of blocks in charge of
carrying the proof. Signing one letter eight times and making the *same* single-date edit
each time gives largest patches of 6, 8, 8, 10, 10, 14, 16, 17 — against 0 to 6 for
untouched and sharpened copies of those same eight. Above the threshold five times out of
eight. The edit is real every time; whether it is *visible* depends on which blocks happened
to carry a bit next to it.

So: an edit to a whole printed value on a page the size of a payout advice is caught
reliably. A single small field on a large scan is not yet reliable, and the honest fix is
not a lower threshold but more carrier — the payload is repeated at most 11 times whatever
the page size, which leaves 69% of a 2000×2600 scan carrying nothing at all.

**Page-wide damage is named rather than drawn.** An online image-text editor runs OCR over
a page, erases the text it finds and redraws it. Measured, that covers 38–67% of the page in
6–10 regions, where honest journeys cover at most 1% in at most 2 and even the largest
single edit covers 14% in 2. Above 20% in 3 or more regions the verdict says the page has
been through an editor and asks for the original file, instead of painting it orange —
because at the pixel level an editor redrawing a line unchanged and a forger changing one
are the same act, and nothing in the signature can separate them.

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
