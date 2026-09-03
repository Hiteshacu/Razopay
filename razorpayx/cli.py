"""Command line for the payout advice verifier.

Three verbs, and deliberately no fourth:

    issue      render and sign a specimen advice
    verify     check an advice against the record RazorpayX kept
    benchmark  measure the detector on a held-out set

There is no `forge`. Producing forgeries is what benchmark.py does internally
to measure recall, and exposing that as a command would ship the attack tool
alongside the defence.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# The engine lives at the repository root; this package sits beside it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _cmd_issue(args: argparse.Namespace) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from .advice import sample_advice
    from .issue import issue

    keys = Path(args.keys)
    keys.mkdir(parents=True, exist_ok=True)
    private, public = keys / "priv.pem", keys / "pub.pem"
    if not private.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        public.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        print(f"generated a signing key pair in {keys}")

    advice = sample_advice(random.Random(args.seed))
    issued = issue(advice, args.out, private_key=private, public_key=public,
                   seed=args.seed)
    print(f"issued   {issued.payout_id}")
    print(f"  amount   Rs {advice.amount_text} by {advice.mode}")
    print(f"  to       {advice.beneficiary_legal}")
    print(f"  image    {issued.image_path}")
    print(f"  record   {Path(args.out) / (issued.payout_id + '.json')}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from utils import read_image

    from .check import GENUINE, check
    from .issue import load_record

    record = load_record(args.record)
    public_pem = Path(args.public_key).read_text(encoding="utf-8")
    image_path = Path(args.image)
    verdict = check(read_image(image_path), image_path, record.printed, public_pem)

    print()
    print(f"  {verdict.status}: {verdict.headline}")
    print(f"  {verdict.detail}")
    if verdict.findings:
        print()
        print("  field checks")
        for finding in verdict.findings:
            mark = "ok " if finding.matched else "BAD"
            print(f"    {mark} {finding.name:14} expected {finding.expected!r}")
            if not finding.matched:
                print(f"        {'':14} document says {finding.read!r}")
    print()
    return 0 if verdict.status == GENUINE else 2


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import breakdown, run, summarise, to_json

    report = run(args.work, advices=args.advices, seed=args.seed)
    print(summarise(report))
    if args.detail:
        print(breakdown(report))
    if args.json:
        to_json(report, args.json)
        print(f"  written to {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="razorpayx",
        description="Detect forged RazorpayX payout advices.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_issue = sub.add_parser("issue", help="render and sign a specimen advice")
    p_issue.add_argument("--out", default="razorpayx_out/issued")
    p_issue.add_argument("--keys", default="razorpayx_out/keys")
    p_issue.add_argument("--seed", type=int, default=1)
    p_issue.set_defaults(func=_cmd_issue)

    p_verify = sub.add_parser("verify", help="check an advice against its record")
    p_verify.add_argument("image")
    p_verify.add_argument("--record", required=True, help="the .json written at issuance")
    p_verify.add_argument("--public-key", required=True)
    p_verify.set_defaults(func=_cmd_verify)

    p_bench = sub.add_parser("benchmark", help="measure on a held-out set")
    p_bench.add_argument("--work", default="razorpayx_bench")
    p_bench.add_argument("--advices", type=int, default=10)
    p_bench.add_argument("--seed", type=int, default=5000,
                         help="5000 is the evaluation split; 1000 was used while developing")
    p_bench.add_argument("--detail", action="store_true", help="per-case breakdown")
    p_bench.add_argument("--json", help="write results to this file")
    p_bench.set_defaults(func=_cmd_benchmark)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
