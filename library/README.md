# trustshield

Sign an image so the proof survives a screenshot.

Most provenance systems put the signature in metadata. A screenshot removes
metadata completely, and so does almost every messaging app. `trustshield`
writes the signature into the image's frequency coefficients instead — into
the same 8×8 blocks JPEG itself works on — so the proof travels with the
picture rather than with the file.

```python
import trustshield

keys = trustshield.KeyPair.generate().save("./keys")

trustshield.sign("notice.png", "signed.png", private_key="./keys")

print(trustshield.verify("signed.png", public_key="./keys"))
# AUTHENTIC: Signature valid and content unchanged.
```

## Install

```bash
pip install trustshield
```

PDF signing needs a renderer, which is large, so it is optional:

```bash
pip install "trustshield[pdf]"
```

Python 3.10+.

## Keys

The two halves do different jobs and must not be confused:

| File | Job | Share it? |
| --- | --- | --- |
| `private_key.pem` | signs | **Never.** Anyone holding it can sign as you. |
| `public_key.pem` | verifies | Yes. It cannot sign, and verification is impossible without it. |

**The same pair must be on both sides.** A document signed with one private
key verifies only against its own public key. Send the public key wherever
verification happens; keep the private key where signing happens.

```python
keys = trustshield.KeyPair.generate().save("./keys")
print(keys.fingerprint[:16])   # a short id for "is this the key I think it is?"

later = trustshield.KeyPair.load("./keys")
```

Keys are written as plain PEM so they travel — to a colleague, into a
container, onto the machine that will verify. Protect the private key the way
you would a password.

## Verifying

`verify()` returns one of four answers, and the difference matters:

| Status | Meaning |
| --- | --- |
| `AUTHENTIC` | Signed by that key, and unchanged since. |
| `TAMPERED` | Genuinely signed by that key — **and edited afterwards**. |
| `SIGNATURE_INVALID` | A proof is present but this key did not validate it. Usually the wrong key. |
| `WATERMARK_NOT_FOUND` | No proof at all: never signed, or damaged past recovery. |

```python
result = trustshield.verify("signed.png", public_key="./keys")

if result:                       # truthy only when AUTHENTIC
    print("genuine")
elif result.status == trustshield.TAMPERED:
    print("issued by that authority, then altered")
```

`TAMPERED` is the interesting one, and it is why the fingerprint is carried
inside the payload as well as signed: the signature is valid, but the picture
no longer matches what was signed. That is someone editing a real notice and
re-sharing it — a case a plain signature cannot distinguish from a valid one.

## Command line

```bash
trustshield keygen -o ./keys
trustshield sign notice.png -o signed.png -k ./keys
trustshield verify signed.png -k ./keys
```

Exit codes, so a pipeline can branch on the answer:

| Code | Meaning |
| --- | --- |
| `0` | signed, or verified as authentic |
| `1` | not authentic |
| `2` | the command could not run at all |

```bash
if trustshield verify incoming.png -k ./public; then
  echo "genuine"
else
  echo "rejected"
fi
```

## What survives, and what does not

| | |
| --- | --- |
| Screenshotting | survives |
| JPEG/PNG recompression | survives |
| Resizing, moderate rescaling | survives |
| Forwarding through messaging apps | survives |
| Stripping metadata | irrelevant — nothing is stored there |
| Heavy cropping | **fails** — the blocks carrying the signature are cut away |
| Photographing a screen | **fails** — moiré and perspective exceed recovery |
| Very small images | **fails** — too few blocks to carry 2,272 bits |

## How it works

1. A **128-bit perceptual fingerprint** of the image — 64-bit dHash plus
   64-bit pHash. It describes how the page *looks*, so recompression barely
   moves it.
2. That fingerprint is **signed** with RSA-2048, PSS padding, SHA-256.
3. Fingerprint and signature are packed into **284 bytes** with a magic
   marker and checksum.
4. Those 2,272 bits are **embedded** across the image's 8×8 DCT blocks, by
   forcing an inequality between mid-frequency coefficient pairs. Block order
   comes from a SHA-256 permutation; bits repeat up to 11× and are recovered
   by majority vote.

Mid-frequency is the whole trick: low frequencies are visible to the eye, high
frequencies are the first thing JPEG discards, and the middle is neither.

Verification tries four recovery strategies in order and stops at the first
that works — direct extraction, registry-assisted re-alignment, screenshot
recovery, then a legacy sweep.

## Where it writes

The engine keeps a small registry and audit trail, used to re-align rescaled
and screenshotted images. By default that lives under your user data directory
(`%LOCALAPPDATA%\trustshield` or `~/.local/share/trustshield`).

Set `DTS_DATA_DIR` to move it — a per-project path is sensible if you want
each project's registry kept separate.

```python
import os
os.environ["DTS_DATA_DIR"] = "./.trustshield"   # before importing trustshield
```

## Limits worth stating plainly

- **Key trust is not solved here.** Verification proves *a* key signed the
  document. Proving that key belongs to a particular organisation needs a
  directory or certificate chain you provide.
- **This is provenance, not detection.** It proves what is genuine; it does
  not analyse an unknown image for signs of synthesis.

## License

MIT.
