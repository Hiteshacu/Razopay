"""The key pair the RazorpayX demo documents are signed with, kept durably.

Both demo routes used to generate their pair into a directory under the
upload root and leave it there. On a host with a real disk that works. On a
container it is a slow-acting trap: the filesystem is rebuilt on every deploy,
the pair is regenerated, and every advice or payslip issued before that
deploy stops verifying — not as ALTERED, which would at least be a claim about
the document, but as NOT_ISSUED, which tells the holder of a genuine page that
RazorpayX never signed it. Observed exactly that way in production: an advice
issued in the morning verified, the service redeployed, and the same file came
back unsigned.

So the pair goes where the authority keys already go. The private half is
Fernet ciphertext under MASTER_KEY, in Firestore or on disk according to
KEY_STORE_BACKEND; the public half needs no secrecy and is a Firestore
document of its own. The container keeps plaintext copies only as a cache,
because sign_poster and verify_poster take paths rather than bytes.

Nothing here is allowed to make signing impossible on a plain checkout. With
no MASTER_KEY and no Firebase project the durable path is skipped and the old
behaviour — a pair on local disk — is what happens, which is the right
outcome for a laptop and the wrong one only where a warning is already printed
at startup.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_PUBLIC_COLLECTION = "demo_public_keys"


def _generate() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _load_durable(authority_id: str) -> tuple[bytes, bytes] | None:
    """The stored pair, or None if there is not a complete one."""
    from .firebase_service import FirebaseService
    from .private_key_store import PrivateKeyStore

    document = FirebaseService().get_document(_PUBLIC_COLLECTION, authority_id)
    if not document or not document.get("public_pem"):
        return None
    private_pem = PrivateKeyStore().load_private_key_bytes(authority_id, f"{authority_id}_demo")
    return private_pem, str(document["public_pem"]).encode("utf-8")


def _save_durable(authority_id: str, private_pem: bytes, public_pem: bytes) -> None:
    from .firebase_service import FirebaseService
    from .private_key_store import PrivateKeyStore

    PrivateKeyStore().save_private_key(authority_id, f"{authority_id}_demo", private_pem)
    FirebaseService().create_document(_PUBLIC_COLLECTION, authority_id, {
        "authority_id": authority_id,
        "public_pem": public_pem.decode("utf-8"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": "Signing key for the RazorpayX demo documents. Public half only.",
    })


def demo_key_pair(authority_id: str, cache_dir: Path) -> tuple[Path, Path]:
    """Paths to the demo pair for `authority_id`, creating it once, ever.

    The cached files are trusted when both are present: they were either
    written from the durable copy by this process or by a previous request in
    the same container, and re-reading Firestore on every signature would cost
    a round trip to prove something that cannot have changed.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    private_path, public_path = cache_dir / "priv.pem", cache_dir / "pub.pem"
    if private_path.exists() and public_path.exists():
        return private_path, public_path

    private_pem = public_pem = None
    try:
        stored = _load_durable(authority_id)
        if stored is not None:
            private_pem, public_pem = stored
    except Exception as exc:
        print(f"WARNING: durable demo key for {authority_id} could not be read: {exc}", flush=True)

    if private_pem is None:
        private_pem, public_pem = _generate()
        try:
            _save_durable(authority_id, private_pem, public_pem)
            # Read back rather than trust what was just written. Two replicas
            # can reach this line at the same moment on a cold start, and the
            # one that loses the race has to end up using the pair that won or
            # half the documents issued in that minute are signed with a key
            # nothing will verify against.
            stored = _load_durable(authority_id)
            if stored is not None:
                private_pem, public_pem = stored
        except Exception as exc:
            print(
                f"WARNING: the {authority_id} demo key pair could not be stored durably "
                f"({exc}). It will be regenerated on the next deploy, and documents "
                "issued with it will stop verifying at that point.",
                flush=True,
            )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    return private_path, public_path
