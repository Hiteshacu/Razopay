from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .utils import PRIVATE_KEY_BACKUP_ROOT, harden_existing_private_key_file
except ImportError:
    from utils import PRIVATE_KEY_BACKUP_ROOT, harden_existing_private_key_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Seal a plaintext private key with Windows DPAPI, lock its file permissions, "
            "and create an encrypted backup inside a locked backup folder."
        )
    )
    parser.add_argument(
        "--path",
        default="private_key.pem",
        help="Path to the private key file to harden.",
    )
    args = parser.parse_args()

    hardened_path = harden_existing_private_key_file(args.path)
    backup_root = Path(PRIVATE_KEY_BACKUP_ROOT)
    print(f"Private key hardened successfully: {hardened_path}")
    print(f"Locked backup root: {backup_root}")


if __name__ == "__main__":
    main()
