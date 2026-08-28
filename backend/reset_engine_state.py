"""Wipe authorities, keys and signed documents for a clean start.

    cd backend
    .venv\\Scripts\\python.exe reset_engine_state.py            # show only
    .venv\\Scripts\\python.exe reset_engine_state.py --yes      # actually delete

Nothing is deleted without --yes. The first run prints exactly what would go,
so the destructive step is always a second, deliberate command.

What it removes:
  * Firestore: authorities, public_keys, private_keys, signed_documents,
    audit_logs, and engine_state/signed_registry
  * Signed files from whichever document store is configured
  * Local scratch and key files under backend/uploads and
    backend/secure_private_keys, plus the on-disk registry

What it keeps:
  * Accounts in admin_users whose email is in KEEP_ACCOUNTS. Every other
    admin_users record is removed, so an account that is not on that list
    goes back to requesting approval the next time it signs in.
  * Firebase Auth itself is untouched. Deleting a sign-in account is not
    this script's business, and an Auth account with no admin_users record
    is simply a new applicant again.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

# backend/ first: the project root holds an app.py that would otherwise
# shadow the backend's own `app` package.
for entry in (str(BACKEND_ROOT), str(PROJECT_ROOT)):
    if entry in sys.path:
        sys.path.remove(entry)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.firebase_client import get_firestore_client  # noqa: E402
from app.services.document_store import get_document_store  # noqa: E402

import utils  # noqa: E402


# The accounts that survive the reset.
KEEP_ACCOUNTS = {
    "hiteshacu@gmail.com",
    "pramilacu@gmail.com",
}

COLLECTIONS = [
    "authorities",
    "public_keys",
    "private_keys",
    "signed_documents",
    "audit_logs",
]


def _count(db, collection: str) -> int:
    return sum(1 for _ in db.collection(collection).stream())


def _wipe_collection(db, collection: str, *, commit: bool) -> int:
    removed = 0
    # Batched, because a per-document round trip against a few hundred
    # records is slow enough to look like a hang.
    batch = db.batch()
    pending = 0
    for snapshot in db.collection(collection).stream():
        removed += 1
        if not commit:
            continue
        batch.delete(snapshot.reference)
        pending += 1
        if pending == 400:  # Firestore caps a batch at 500 writes
            batch.commit()
            batch = db.batch()
            pending = 0
    if commit and pending:
        batch.commit()
    return removed


def _wipe_accounts(db, *, commit: bool) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    removed: list[str] = []
    for snapshot in db.collection("admin_users").stream():
        record = snapshot.to_dict() or {}
        email = (record.get("email") or "").strip().lower()
        if email in KEEP_ACCOUNTS:
            kept.append(email or snapshot.id)
            continue
        removed.append(email or snapshot.id)
        if commit:
            snapshot.reference.delete()
    return kept, removed


def _wipe_stored_files(db, *, commit: bool) -> int:
    """Delete the signed file behind every document record.

    Driven from the records rather than by listing the bucket: the store may
    hold objects this deployment did not write, and a reset should not reach
    beyond its own data.
    """
    store = get_document_store()
    removed = 0
    for snapshot in db.collection("signed_documents").stream():
        key = (snapshot.to_dict() or {}).get("signed_file_storage_path")
        if not key:
            continue
        removed += 1
        if commit:
            try:
                store.delete(key)
            except Exception as exc:  # a stubborn object must not stop the reset
                print(f"    ! could not delete {key}: {exc}")
    return removed


def _local_targets() -> list[Path]:
    return [
        settings.signed_documents_dir,
        settings.original_documents_dir,
        settings.temp_dir,
        Path(settings.secure_keys_dir if Path(settings.secure_keys_dir).is_absolute()
             else BACKEND_ROOT / settings.secure_keys_dir),
        utils.SIGNED_REGISTRY_PATH,
        utils.AUDIT_LOG_ROOT,
        utils.PRIVATE_KEY_BACKUP_ROOT,
    ]


def _clear_read_only(path: Path) -> None:
    """Make a path deletable again.

    The engine chmods the registry and the key backups read-only after every
    write, as a tamper check (utils._set_read_only). On Windows that makes
    unlink fail outright with "Access is denied" rather than merely warn, so
    a reset has to undo the protection it is about to delete.
    """
    try:
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass


def _on_remove_error(func, path, _exc) -> None:
    _clear_read_only(Path(path))
    try:
        func(path)
    except OSError:
        pass


# onerror was replaced by onexc in 3.12; both hand the callback the same
# three positional arguments, so one handler serves either.
_RMTREE_KW = {"onexc": _on_remove_error} if sys.version_info >= (3, 12) else {"onerror": _on_remove_error}


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, **_RMTREE_KW)
    else:
        _clear_read_only(path)
        path.unlink(missing_ok=True)


def _wipe_local(*, commit: bool) -> list[str]:
    touched: list[str] = []
    for target in _local_targets():
        # Each target is independent: one stubborn path used to abandon the
        # whole rest of the cleanup partway through.
        try:
            if target.is_dir():
                children = list(target.iterdir())
                if not children:
                    continue
                touched.append(f"{target} ({len(children)} entries)")
                if commit:
                    for child in children:
                        _remove(child)
            elif target.is_file():
                touched.append(str(target))
                if commit:
                    _remove(target)
        except OSError as exc:
            touched.append(f"{target}  ! FAILED: {exc}")
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="actually delete. Without it, nothing is written.",
    )
    args = parser.parse_args()
    commit = args.yes

    db = get_firestore_client()

    print()
    print("Clean start" if commit else "Clean start — DRY RUN, nothing will be deleted")
    print(f"  document store : {settings.document_store_backend}")
    print(f"  keeping        : {', '.join(sorted(KEEP_ACCOUNTS))}")
    print()

    print("Signed files in the document store")
    files = _wipe_stored_files(db, commit=commit)
    print(f"  {'deleted' if commit else 'would delete'} {files} file(s)")
    print()

    print("Firestore collections")
    for collection in COLLECTIONS:
        count = _wipe_collection(db, collection, commit=commit) if commit else _count(db, collection)
        print(f"  {collection:<20} {'deleted' if commit else 'would delete'} {count} record(s)")

    registry = db.collection("engine_state").document("signed_registry")
    exists = registry.get().exists
    print(f"  {'engine_state/signed_registry':<20} "
          f"{'deleted' if commit else 'would delete'} {1 if exists else 0} record(s)")
    if commit and exists:
        registry.delete()
    print()

    print("Accounts")
    kept, removed = _wipe_accounts(db, commit=commit)
    for email in sorted(kept):
        print(f"  keep    {email}")
    for email in sorted(removed):
        print(f"  {'remove ' if commit else 'would remove'} {email}")
    if not removed:
        print("  (nothing to remove)")
    print()

    print("Local files")
    touched = _wipe_local(commit=commit)
    for line in touched:
        print(f"  {'cleared' if commit else 'would clear'} {line}")
    if not touched:
        print("  (nothing to clear)")
    print()

    if commit:
        print("Done. Create a fresh authority and key from the console.")
    else:
        print("Nothing was deleted. Re-run with --yes to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
