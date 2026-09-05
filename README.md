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
payload was repeated **at most 11 times whatever the page size**, so the share of blocks
carrying a bit at all fell as the page grew — and a block carrying no bit cannot report
damage:

| Page | Blocks | Carried a bit | Now |
|---|---|---|---|
| Payout advice, 1000×1400 | 21,875 | 93% | 93% |
| Scanned letter, 1400×1750 | 38,150 | 66% | **89%** |
| Phone photo of one, 2000×2600 | 81,250 | 31% | **98%** |

Two thirds of every edit on a large page was invisible by construction, and *which* third
showed depended on where the permutation happened to put the carriers. Since RSA-PSS salts
every signature, that made detection a coin flip: one date changed on one letter, signed
eight times, gave largest patches of 6, 8, 8, 10, 10, 14, 16, 17 — over the line five times
out of eight.

The cap is gone. A page now carries a bit in every block it has room for, and a reader tries
both counts, so documents signed before this still verify. Same test, after: **15, 19, 22,
23, 25, 38, 45, 45 — eight out of eight**, against 0 for every untouched copy.

Two further things follow from the geometry. A window asking *"is this patch solid?"* has to
grow as the share of carriers falls, or it reads a block holding nothing as a block that is
fine. And it has to ask for **enough** flattened carriers and for **a solid share** of them
as two separate conditions — as one condition ("all of them"), giving a page more bits to
carry made it strictly harder to pass, so raising the capacity made detection worse before it
made it better.

## Measured results

Held-out evaluation split (seed 5000); thresholds were fixed on a development split
(seed 1000) and never refitted.

**Carrier tamper detection.** Two corpora, each split into a development set the thresholds
were fixed on and a held-out set they were never refitted against: payout advices at
1000×1400, and scanned-letter pages at 1400×1750 through 2000×2500. 198 honest copies,
232 edits.

| Detector | False accusations | Missed edits |
|---|---|---|
| Fixed window, 11-copy cap | 0 of 198 | 61 of 232 |
| Window sized to carrier density | 0 of 198 | 23 of 232 |
| Full capacity, evidence and solidity split | **0 of 198** | **11 of 232** |

Per split for the last of those: advices 4 of 65 and 5 of 104; letters 0 of 21 and 2 of 42.

The threshold is 12, the worst honest journey plus one — a sharpened advice reaches 11. That
is tighter than a threshold should sit, and 13 is where it would sit if there were a choice.
There is not: a run of edits land on exactly 12, so 13 turns 11 misses into 39. The cliff
decides it, and it is recorded rather than smoothed over.

**On spread.** RSA-PSS salts every signature, so signing the same page twice puts a different
set of blocks in charge of the proof, and every count here moves a little between runs. That
used to decide outcomes. With the page carrying every bit it has room for it no longer does,
but these are measurements rather than constants.

**Page-wide damage is named rather than drawn.** An online image-text editor runs OCR over a
page, erases the text it finds and redraws it. Measured, that leaves 68–100% of the page
inside a region, where honest journeys reach 6% and even the largest single edit — a doubled
amount repainting both the headline and the table row — reaches 15%. Above 35% the verdict
says the page has been through an editor and asks for the original file, instead of painting
it orange. It cannot do better than name it: at the pixel level, an editor redrawing a line
unchanged and a forger changing one are the same act, and nothing in the signature separates
them.

**Region localisation** — 1 edit gives 1 box, 2 give 2, 3 give 3, each on the field that
was actually repainted.

**Payout advice benchmark** (`python -m razorpayx.cli benchmark --advices 4 --seed 5000`)

```
Forgeries rejected      76 / 76      recall     1.000
Falsely accused          0 / 40      precision  1.000
Genuine passed          36 / 40      FPR        0.000
```

**Payslips** — the same detector, unchanged: genuine slips pass, and erasing one digit of
net pay is caught and boxed.

## Checking against the copy that was filed

The carrier answers from the file alone, which is the right default: no lookup, no
account, and a document issued a year ago answers as well as one issued a minute ago.
There is one page it cannot answer for.

An online image-text editor runs OCR over a page, erases every line of text it finds and
redraws it. Every line is then new pixels, so the carrier is broken along all of them —
and nothing in the signature distinguishes a line the editor redrew *unchanged* from a
line a forger *changed*. Both are the same act on the same pixels.

Content can tell them apart, but only against something. That something is the copy the
object store already keeps from signing time. Each 16×16 block of the page is matched
against a small neighbourhood of that copy and scored on the best match found, so a line
redrawn a pixel to the left matches itself a pixel to the left, and a changed digit
matches nothing.

Finding the filed copy takes two routes. The signature carried in the pixels names it
exactly. Where an editor has destroyed the signature, the 128-bit perceptual fingerprint
still identifies it: measured, the same document lands 2–7 bits away after WhatsApp, JPEG
quality 20, a photograph of a screen, a watermark, or a full re-typeset, while unrelated
documents land at 65–67. That identifies the page; it never authenticates it, and where
the signature is gone the verdict says so.

| Case | Result |
|---|---|
| Untouched, and 19 honest journeys (JPEG down to q20, WhatsApp, screenshot, photo of a screen, greyscale, ±8% brightness) | no boxes |
| Editor's watermark tiled over the page | no boxes |
| Whole page re-typeset by an editor, nothing changed | no boxes, and the verdict says the file was re-saved but every word matches |
| One date changed | **one red box, on the date** |
| One date changed, under the watermark | **one red box, on the date** |
| One date changed, on a fully re-typeset page | **one red box, on the date** |

0 false alarms in 19 honest journeys, and the changed field boxed in every case that had
one. A red box is a claim about the document — *this is not what it said* — so it does not
share a colour with the amber carrier box, which is the softer claim that some pixel was
repainted.

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
python -m razorpayx.cli benchmark --advices 4 --seed 5000 --detail
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
