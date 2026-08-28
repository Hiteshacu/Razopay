"""RSA key pairs for signing and verifying documents.

The two halves are not interchangeable and the distinction matters:

  private_key.pem   signs.    Never share it. Anyone holding it can issue
                              documents in your name.
  public_key.pem    verifies. Publish it freely — it is useless for signing,
                              and verification is impossible without it.

The same pair must be used on both sides: a document signed with one private
key verifies only against its own public key.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DEFAULT_KEY_SIZE = 2048
PRIVATE_KEY_NAME = "private_key.pem"
PUBLIC_KEY_NAME = "public_key.pem"


class KeyError_(Exception):
    """A key could not be read, written or understood."""


@dataclass(frozen=True)
class KeyPair:
    """An RSA key pair, and where it was written."""

    private_key: rsa.RSAPrivateKey
    public_key: rsa.RSAPublicKey
    private_path: Path | None = None
    public_path: Path | None = None

    # ---------------------------------------------------------------- create

    @classmethod
    def generate(cls, key_size: int = DEFAULT_KEY_SIZE) -> "KeyPair":
        """A fresh pair, held in memory until you call save().

        2048 bits is the default because the payload embedded in the image is
        sized for it: a 2048-bit signature is 256 bytes of the 284-byte
        payload. A 4096-bit key doubles that to 512 and needs an image with
        roughly twice the blocks to carry it with the same redundancy.
        """
        if key_size < 2048:
            raise ValueError("Refusing to generate a key below 2048 bits.")
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        return cls(private_key=private_key, public_key=private_key.public_key())

    # ------------------------------------------------------------------ save

    def save(self, directory: str | Path, *, overwrite: bool = False) -> "KeyPair":
        """Write both halves as PEM files and return the pair with its paths.

        Plain PEM, deliberately. The engine's own key store seals private keys
        to the machine that wrote them, which is right for a server and wrong
        here: a library key has to travel — to a colleague, into a container,
        onto the machine that will verify. A key that only works where it was
        made is not a key you can build on.

        The file is created readable only by you where the platform supports
        it. That is a courtesy, not a security boundary; treat the private key
        the way you would treat a password.
        """
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)

        private_path = target / PRIVATE_KEY_NAME
        public_path = target / PUBLIC_KEY_NAME

        if not overwrite:
            existing = [p for p in (private_path, public_path) if p.exists()]
            if existing:
                names = ", ".join(p.name for p in existing)
                # Name the fix, not just the rule. Hitting this almost always
                # means someone meant to reuse a key pair rather than make a
                # new one — keys are generated once and kept.
                where = str(directory)
                raise FileExistsError(
                    f"{names} already exists in {target}.\n"
                    f"To use the existing pair:  KeyPair.load({where!r})\n"
                    f"To replace it:             "
                    f"KeyPair.generate().save({where!r}, overwrite=True)\n"
                    f"Replacing is destructive — anything signed with the old key "
                    f"stops verifying."
                )

        private_bytes = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        private_path.write_bytes(private_bytes)
        try:
            private_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # Windows and some filesystems do not honour this

        public_path.write_bytes(
            self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

        return KeyPair(
            private_key=self.private_key,
            public_key=self.public_key,
            private_path=private_path,
            public_path=public_path,
        )

    # ------------------------------------------------------------------ load

    @classmethod
    def load(cls, directory: str | Path) -> "KeyPair":
        """Read a pair previously written by save()."""
        target = Path(directory)
        private_path = target / PRIVATE_KEY_NAME
        public_path = target / PUBLIC_KEY_NAME
        if not private_path.is_file():
            raise FileNotFoundError(f"No {PRIVATE_KEY_NAME} in {target}")

        private_key = load_private_key(private_path)
        public_key = (
            load_public_key(public_path) if public_path.is_file() else private_key.public_key()
        )
        return cls(
            private_key=private_key,
            public_key=public_key,
            private_path=private_path,
            public_path=public_path if public_path.is_file() else None,
        )

    @property
    def key_size(self) -> int:
        return self.public_key.key_size

    @property
    def fingerprint(self) -> str:
        """A short, stable identifier for the public half.

        Use it to check that the key verifying a document is the key you
        think it is, without comparing whole PEM files by eye.
        """
        import hashlib

        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(pem).hexdigest()


def load_private_key(path: str | Path) -> rsa.RSAPrivateKey:
    """Read an unencrypted PEM private key."""
    raw = Path(path).read_bytes()
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except TypeError as exc:
        raise KeyError_(
            f"{path} is password-protected. trustshield reads unencrypted PEM keys; "
            f"decrypt it first with: openssl rsa -in {path} -out decrypted.pem"
        ) from exc
    except ValueError as exc:
        raise KeyError_(f"{path} is not a readable PEM private key: {exc}") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise KeyError_(f"{path} is not an RSA key. trustshield signs with RSA-PSS.")
    return key


def load_public_key(path: str | Path) -> rsa.RSAPublicKey:
    """Read a PEM public key."""
    raw = Path(path).read_bytes()
    try:
        key = serialization.load_pem_public_key(raw)
    except ValueError as exc:
        raise KeyError_(f"{path} is not a readable PEM public key: {exc}") from exc
    if not isinstance(key, rsa.RSAPublicKey):
        raise KeyError_(f"{path} is not an RSA public key.")
    return key
