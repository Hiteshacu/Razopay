"""Command line interface: trustshield keygen | sign | verify.

Exists so signing can be a step in a build, a cron job or a CI pipeline
without anyone writing Python around it.

Exit codes are meaningful, because a script needs to branch on the answer:

    0   success — signed, or verified as authentic
    1   the document is not authentic (any of the three reasons)
    2   the command could not be carried out at all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .api import AUTHENTIC, SigningError, sign, verify
from .keys import KeyPair

EXIT_OK = 0
EXIT_NOT_AUTHENTIC = 1
EXIT_FAILED = 2


def _keygen(args: argparse.Namespace) -> int:
    directory = Path(args.out)
    try:
        pair = KeyPair.generate(key_size=args.bits).save(directory, overwrite=args.force)
    except FileExistsError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_FAILED

    print(f"private key  {pair.private_path}")
    print(f"public key   {pair.public_path}")
    print(f"key size     {pair.key_size} bits")
    print(f"fingerprint  {pair.fingerprint[:32]}")
    print()
    print("Keep the private key secret — anyone holding it can sign as you.")
    print("Share the public key with whoever needs to verify.")
    return EXIT_OK


def _sign(args: argparse.Namespace) -> int:
    try:
        result = sign(
            args.image,
            args.output,
            private_key=args.key,
            self_check=not args.no_self_check,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_FAILED
    except SigningError as exc:
        print(f"Signing failed: {exc}", file=sys.stderr)
        return EXIT_FAILED

    print(f"signed  {result.output_path}")
    return EXIT_OK


def _verify(args: argparse.Namespace) -> int:
    try:
        result = verify(args.image, public_key=args.key)
    except (FileNotFoundError, ValueError) as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_FAILED

    print(f"{result.status}")
    print(f"{result.detail}")
    return EXIT_OK if result.status == AUTHENTIC else EXIT_NOT_AUTHENTIC


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trustshield",
        description="Sign documents so the proof survives a screenshot.",
    )
    parser.add_argument("--version", action="version", version=f"trustshield {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    keygen = sub.add_parser("keygen", help="create an RSA key pair")
    keygen.add_argument("-o", "--out", default="./keys", help="directory to write into (default: ./keys)")
    keygen.add_argument("--bits", type=int, default=2048, help="key size (default: 2048)")
    keygen.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing keys — anything signed with the old key stops verifying",
    )
    keygen.set_defaults(func=_keygen)

    signer = sub.add_parser("sign", help="write a signature into a document")
    signer.add_argument("image", help="PNG, JPG or PDF to sign")
    signer.add_argument("-o", "--output", default=None, help="where to write (default: <name>_signed.<ext>)")
    signer.add_argument("-k", "--key", required=True, help="private key file, or the directory holding it")
    signer.add_argument(
        "--no-self-check",
        action="store_true",
        help="skip reading the signature back after writing it — faster, and you lose the guarantee",
    )
    signer.set_defaults(func=_sign)

    verifier = sub.add_parser("verify", help="check a document")
    verifier.add_argument("image", help="the file to check")
    verifier.add_argument("-k", "--key", required=True, help="public key file, or the directory holding it")
    verifier.set_defaults(func=_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
