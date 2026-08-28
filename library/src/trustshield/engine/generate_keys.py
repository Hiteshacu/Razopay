from __future__ import annotations

import argparse

from cryptography.hazmat.primitives.asymmetric import rsa

try:
    from .utils import log_signing_event, save_private_key, save_public_key
except ImportError:
    from utils import log_signing_event, save_private_key, save_public_key


def generate_keys() -> tuple[str, str]:
    """Generate a 2048-bit RSA key pair for signing and verification."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_path = save_private_key(private_key)
    public_path = save_public_key(public_key)
    log_signing_event(
        "key_pair_generated",
        asset_type="private_key",
        private_key_path=private_path,
        public_key_path=public_path,
        key_size_bits=2048,
    )
    return str(private_path), str(public_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RSA keys for Digital Trust Shield.")
    parser.parse_args()

    generate_keys()
    print("RSA keys generated successfully")


if __name__ == "__main__":
    main()
