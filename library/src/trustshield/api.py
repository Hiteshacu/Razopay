"""Sign a document, and check one.

Two functions and two result objects. Everything harder than this — the
perceptual fingerprint, the DCT embedding, the four-tier recovery — is the
engine's business and does not need to be yours.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .keys import PRIVATE_KEY_NAME, PUBLIC_KEY_NAME

#: Statuses a verification can return.
AUTHENTIC = "AUTHENTIC"
TAMPERED = "TAMPERED"
SIGNATURE_INVALID = "SIGNATURE_INVALID"
WATERMARK_NOT_FOUND = "WATERMARK_NOT_FOUND"
ERROR = "ERROR"

SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}


class SigningError(Exception):
    """A document could not be signed."""


@dataclass(frozen=True)
class SignResult:
    """What came out of signing."""

    output_path: Path
    signature: str
    #: Where the signed file was written, for printing to a user.
    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"signed -> {self.output_path}"


@dataclass(frozen=True)
class VerifyResult:
    """What a check concluded.

    `authentic` is the one-line answer. `status` says why, which matters
    because "not authentic" covers two very different situations: a document
    that was never signed, and a genuine document that has since been edited.
    """

    status: str
    detail: str

    @property
    def authentic(self) -> bool:
        return self.status == AUTHENTIC

    def __bool__(self) -> bool:
        return self.authentic

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.status}: {self.detail}"


def _resolve_key(key: str | Path, filename: str) -> Path:
    """Accept either a key file or the directory holding one."""
    path = Path(key)
    if path.is_dir():
        candidate = path / filename
        if not candidate.is_file():
            raise FileNotFoundError(f"No {filename} in {path}")
        return candidate
    if not path.is_file():
        raise FileNotFoundError(f"No such key file: {path}")
    return path


def _check_input(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(f"{path.suffix or 'that'} is not supported. Use one of: {supported}")



def _public_pem_for(private_key_path: Path) -> Path:
    """Write the public half of a private key to a temporary PEM file."""
    import tempfile

    from cryptography.hazmat.primitives import serialization

    from .keys import load_private_key

    private_key = load_private_key(private_key_path)
    pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
    try:
        handle.write(pem)
    finally:
        handle.close()
    return Path(handle.name)


def sign(
    image: str | Path,
    output: str | Path | None = None,
    *,
    private_key: str | Path,
    self_check: bool = True,
) -> SignResult:
    """Write a signature into a document's pixels.

    `private_key` may be the PEM file itself or the directory holding it.

    `self_check` reads the signature straight back out of the file just
    written and fails loudly if it cannot be recovered. Leave it on. It is
    the difference between believing a document is signed and knowing it,
    and the cost is one extra extraction pass.
    """
    source = Path(image)
    _check_input(source)
    key_path = _resolve_key(private_key, PRIVATE_KEY_NAME)

    if output is None:
        output = source.with_name(f"{source.stem}_signed{source.suffix}")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)

    from .engine.sign_poster import sign_poster

    # The self-check reads the signature back out of the file it just wrote,
    # which means verifying — which needs the public half. Rather than asking
    # the caller for a key they already implicitly gave us, derive it: a
    # public key is always recoverable from its private key, so there is no
    # situation where the caller has one and not the other.
    #
    # Without this the engine falls back to its own default public key path,
    # which inside an installed package points into site-packages and does
    # not exist — signing then fails with a confusing missing-file error.
    public_pem = _public_pem_for(key_path)
    try:
        signature, written = sign_poster(
            source,
            destination,
            private_key_path=key_path,
            public_key_path=public_pem,
            self_check=self_check,
        )
    except Exception as exc:  # the engine raises a variety of types
        raise SigningError(str(exc) or exc.__class__.__name__) from exc
    finally:
        public_pem.unlink(missing_ok=True)

    return SignResult(
        output_path=Path(written),
        signature=signature if isinstance(signature, str) else str(signature),
    )


def _classify(message: str) -> tuple[str, str]:
    """Turn an engine failure into one of the four answers.

    Deliberately the same mapping the hosted service uses, so a document
    checked through the library and the same document checked through the
    API do not disagree about what happened to it.
    """
    lowered = (message or "").lower()

    # Order matters. Every "recovered, but ..." message also contains the word
    # "watermark", so the specific verdicts have to be tested before the
    # generic nothing-was-found rules or they are swallowed by them.

    # A proof was recovered; this key did not validate it. Usually the wrong
    # authority was selected rather than a forgery.
    if "did not validate" in lowered:
        return SIGNATURE_INVALID, (
            "A proof was found, but the signature did not verify under this key."
        )

    # A proof was recovered and validated; the picture has since changed.
    if "fingerprint did not match" in lowered or "content did not match" in lowered:
        return TAMPERED, (
            "The signature is valid, but the image no longer matches what was signed."
        )

    # A partial or corrupted payload came back. Nothing was proved either way,
    # so this is the same answer as finding nothing at all.
    if "length does not match" in lowered or "length is invalid" in lowered:
        return WATERMARK_NOT_FOUND, "No complete proof could be recovered from this image."

    if (
        "watermark" in lowered
        or "recovery could not" in lowered
        or "time budget" in lowered
        or "timed out" in lowered
    ):
        return WATERMARK_NOT_FOUND, "No hidden proof was found in this image."

    return ERROR, message


def verify(image: str | Path, *, public_key: str | Path) -> VerifyResult:
    """Check a document against a public key.

    Must be the public half of the pair that signed it. A valid document
    checked against the wrong key returns SIGNATURE_INVALID, which is the
    same answer a forgery gives — so if you are surprised by that result,
    check the key before you conclude anything about the document.
    """
    source = Path(image)
    _check_input(source)
    key_path = _resolve_key(public_key, PUBLIC_KEY_NAME)

    from .engine.verify_poster import verify_poster

    try:
        outcome = verify_poster(source, public_key_path=key_path, audit=False)
    except Exception as exc:
        status, detail = _classify(str(exc) or exc.__class__.__name__)
        return VerifyResult(status=status, detail=detail)

    # Images return (bool, message); PDFs return a richer structure.
    if isinstance(outcome, tuple):
        valid, message = outcome
        if valid:
            return VerifyResult(AUTHENTIC, message or "Signature valid and content unchanged.")
        status, detail = _classify(message)
        return VerifyResult(status, detail)

    if isinstance(outcome, dict):
        valid = bool(outcome.get("valid"))
        message = str(outcome.get("message") or "")
        if valid:
            return VerifyResult(AUTHENTIC, message or "Signature valid and content unchanged.")
        status, detail = _classify(message)
        return VerifyResult(status, detail)

    if isinstance(outcome, list):  # per-page results
        pages = len(outcome)
        good = sum(1 for page in outcome if page.get("valid"))
        if good == pages and pages:
            return VerifyResult(AUTHENTIC, f"All {pages} pages verified.")
        return VerifyResult(TAMPERED, f"{good} of {pages} pages verified.")

    return VerifyResult(ERROR, "The engine returned an unrecognised result.")
