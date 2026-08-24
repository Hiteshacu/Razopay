# Publication Policy

Digital Trust Shield contains security-sensitive implementation code. The public GitHub repository is intentionally limited to project documentation, architecture, demo flow, and non-secret configuration examples.

## Published

- Product explanation.
- Architecture diagrams.
- Demo script.
- Security model.
- Environment variable examples.
- High-level API descriptions.

## Not Published

- Private keys and key backups.
- Firebase service account credentials.
- Runtime `.env` files.
- Full signing and verification implementation.
- DCT watermark embedding and extraction source code.
- Screenshot recovery and registry matching implementation.
- Android application source code.
- Admin portal source code.
- Generated QA datasets, screenshots, videos, payment images, and logs.

## Why The Core Code Is Private

The verification engine contains defensive logic for cryptographic proof extraction, resilient watermark recovery, registry matching, and screenshot handling. Publishing the full implementation would make it easier for attackers to study thresholds, build bypasses, or forge demo-specific artifacts.

The public repository explains the architecture while keeping the sensitive engineering private.

## Safe Collaboration Model

For reviewers, judges, or collaborators who need access to the private implementation, share it through a controlled private repository or direct review session rather than the public GitHub repository.
