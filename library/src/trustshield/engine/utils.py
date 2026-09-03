from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import platform
import stat
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils as asym_utils
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parent
# Everything the engine writes at runtime lives under DATA_DIR. On a cloud host
# this points at a mounted persistent disk so the registry and audit trail
# survive a redeploy; locally it stays inside the project folder.
DATA_DIR = Path(os.getenv("DTS_DATA_DIR") or PROJECT_DIR)
PRIVATE_KEY_PATH = PROJECT_DIR / "private_key.pem"
PUBLIC_KEY_PATH = PROJECT_DIR / "public_key.pem"
PRIVATE_KEY_BACKUP_ROOT = DATA_DIR / ".private_key_backups"
AUDIT_LOG_ROOT = DATA_DIR / "audit_logs"
SIGNING_AUDIT_LOG_PATH = AUDIT_LOG_ROOT / "signing_audit.log"
VERIFICATION_AUDIT_LOG_PATH = AUDIT_LOG_ROOT / "verification_audit.log"
SIGNED_REGISTRY_PATH = DATA_DIR / "official_registry.json"
SIGNED_POSTER_PATH = PROJECT_DIR / "signed_poster.png"
FORWARDED_POSTER_PATH = PROJECT_DIR / "forwarded_poster.jpg"
TAMPERED_POSTER_PATH = PROJECT_DIR / "tampered_poster.png"
SAMPLE_POSTER_PATH = PROJECT_DIR / "demo_poster.png"

BLOCK_SIZE = 8
RSA_SIGNATURE_BYTES = 256
WATERMARK_MAGIC = b"DTS2"
WATERMARK_CHECKSUM_BYTES = 4
WATERMARK_SHUFFLE_SEED = 204857
COEFF_A = (3, 2)
COEFF_B = (2, 3)
LEGACY_WATERMARK_COEFFICIENT_PAIRS = (((3, 2), (2, 3)),)
BLUR_RESISTANT_WATERMARK_COEFFICIENT_PAIRS = (
    ((3, 2), (2, 3)),
    ((2, 1), (1, 2)),
)
WATERMARK_EMBED_COEFFICIENT_PAIRS = BLUR_RESISTANT_WATERMARK_COEFFICIENT_PAIRS
WATERMARK_EXTRACT_COEFFICIENT_LAYOUTS = (
    WATERMARK_EMBED_COEFFICIENT_PAIRS,
    LEGACY_WATERMARK_COEFFICIENT_PAIRS,
)
# The first rung is what almost every document is signed at: escalation only
# happens when the full self-check runs and fails, and the payments path forces
# the fast check because simulating a messaging round trip per advice is time a
# synchronous API does not have.
#
# So the first rung decides robustness in practice, and it was measured rather
# than chosen. Over 40 genuine advices through ten journeys each, with the
# registry fallback active:
#
#   strength 24   35/40   loses a JPEG at quality 35
#   strength 36   36/40   survives it
#   strength 48   36/40   buys nothing further
#
# The cost is visibility, since the carrier is the mark: 24 renders at 35.5 dB
# PSNR against the unsigned page, 36 at 33.9 dB, 48 at 32.5 dB. Paying 1.6 dB
# to stop calling a genuine advice unsigned is worth it — a false "not issued"
# is the expensive error here, and the document is a printed form rather than a
# photograph, where a mark at 34 dB is not what anyone is looking at.
#
# A photo of a screen fails at every strength tested. That is geometry, not
# signal: rescreening and perspective break the 8x8 block grid the carrier is
# read from, and no amount of amplitude repairs a grid that has moved.
AUTO_EMBED_STRENGTHS = (36.0, 48.0)
BASE_EMBED_STRENGTH = AUTO_EMBED_STRENGTHS[0]
MAX_REPETITION = 11
PAYLOAD_VERSION = 2
REFERENCE_FINGERPRINT_BYTES = 16
DHASH_BITS = 64
PHASH_BITS = 64
TOTAL_FINGERPRINT_BITS = DHASH_BITS + PHASH_BITS
# These thresholds are intentionally tight now that signing performs a
# forwarded-share self-check. That keeps moderate recompression working while
# making localized poster edits much less likely to slip through.
MAX_TOTAL_FINGERPRINT_DISTANCE = 6
MAX_DHASH_DISTANCE = 4
MAX_PHASH_DISTANCE = 3
SCREENSHOT_REGISTRY_MAX_TOTAL_DISTANCE = 4
SCREENSHOT_REGISTRY_MAX_DHASH_DISTANCE = 2
SCREENSHOT_REGISTRY_MAX_PHASH_DISTANCE = 3
SCREENSHOT_RECOVERY_MAX_TOTAL_DISTANCE = 8
SCREENSHOT_RECOVERY_MAX_DHASH_DISTANCE = 6
SCREENSHOT_RECOVERY_MAX_PHASH_DISTANCE = 4
SEALED_KEY_FORMAT = "dts-sealed-private-key-v1"
DPAPI_DESCRIPTION = "Digital Trust Shield private key"
AUDIT_LOG_PATH = PRIVATE_KEY_BACKUP_ROOT / "security_events.log"
FORWARDED_SHARE_MAX_DIM = 1600
FORWARDED_SHARE_JPEG_QUALITY = 62
_REGISTRY_CACHE_DATA: dict[str, object] | None = None
_REGISTRY_CACHE_MTIME_NS: int | None = None
_REGISTRY_DIMENSION_CACHE: dict[str, tuple[int, int] | None] = {}
# Optional external home for the signed-asset registry. Left unset the engine
# reads and writes official_registry.json as before, which is what the CLI and
# local demo expect. A host without durable local storage installs a backend
# here instead so the registry survives a restart. The engine only requires
# two methods, load() and save(data), so it stays free of any cloud SDK.
_REGISTRY_STORAGE: object | None = None


def set_registry_storage(storage: object | None) -> None:
    """Route registry reads and writes through an external backend."""
    global _REGISTRY_STORAGE, _REGISTRY_CACHE_DATA, _REGISTRY_CACHE_MTIME_NS
    global _REGISTRY_DIMENSION_CACHE
    _REGISTRY_STORAGE = storage
    _REGISTRY_CACHE_DATA = None
    _REGISTRY_CACHE_MTIME_NS = None
    _REGISTRY_DIMENSION_CACHE = {}


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def current_windows_identity() -> str:
    domain = os.environ.get("USERDOMAIN")
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "current_user"
    return f"{domain}\\{username}" if domain else username


def log_security_event(event: str, **details: object) -> None:
    PRIVATE_KEY_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    harden_private_key_permissions(PRIVATE_KEY_BACKUP_ROOT, is_directory=True)
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "details": details,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    harden_private_key_permissions(AUDIT_LOG_PATH)


def harden_private_key_permissions(path: str | Path, is_directory: bool = False) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if is_windows():
        identity = current_windows_identity()
        grant = f"{identity}:(OI)(CI)(F)" if is_directory else f"{identity}:(F)"
        commands = [
            ["icacls", str(target), "/inheritance:r"],
            ["icacls", str(target), "/grant:r", grant],
            ["icacls", str(target), "/remove:g", "*S-1-1-0", "*S-1-5-11", "*S-1-5-32-545"],
        ]
        for command in commands:
            try:
                subprocess.run(command, check=True, capture_output=True)
            except Exception:
                # Keep the project usable even if the host denies ACL changes.
                pass
    else:
        mode = stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if is_directory else 0)
        try:
            os.chmod(target, mode)
        except Exception:
            pass


def _set_read_only(path: str | Path, enabled: bool = True) -> None:
    target = Path(path)
    try:
        if enabled:
            os.chmod(target, stat.S_IREAD)
        else:
            os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
    except Exception:
        pass


def make_public_bundle_readable(path: str | Path) -> None:
    target = Path(path)
    if not target.exists():
        return

    if is_windows():
        commands = [
            ["icacls", str(target), "/inheritance:e"],
            ["icacls", str(target), "/grant:r", "*S-1-1-0:(R)"],
            ["icacls", str(target), "/grant:r", f"{current_windows_identity()}:(F)"],
        ]
        for command in commands:
            try:
                subprocess.run(command, check=True, capture_output=True)
            except Exception:
                pass
        return

    try:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        pass


def _initialize_audit_log(log_path: str | Path, title: str) -> Path:
    target = Path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    harden_private_key_permissions(target.parent, is_directory=True)
    if not target.exists():
        _set_read_only(target, enabled=False)
        target.write_text(
            (
                f"Digital Trust Shield {title}\n"
                "Format: append-only text log with SHA-256 hash chaining\n"
                "Editing or deleting past entries breaks the hash chain.\n\n"
            ),
            encoding="utf-8",
        )
    harden_private_key_permissions(target)
    _set_read_only(target, enabled=True)
    return target


def _last_audit_hash(log_path: str | Path) -> str:
    target = _initialize_audit_log(log_path, "Audit Log")
    content = target.read_text(encoding="utf-8")
    marker = "Entry Hash: "
    position = content.rfind(marker)
    if position == -1:
        return "0" * 64
    return content[position + len(marker) :].splitlines()[0].strip()


def _format_audit_value(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value) if value else "none"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return "none"
    return str(value)


def _append_audit_entry(log_path: str | Path, title: str, event: str, result: str, **details: object) -> Path:
    target = _initialize_audit_log(log_path, title)
    timestamp = datetime.now(timezone.utc).isoformat()
    actor = current_windows_identity()
    previous_hash = _last_audit_hash(target)
    normalized_details = {key: _format_audit_value(value) for key, value in sorted(details.items())}
    entry_payload = {
        "actor": actor,
        "details": normalized_details,
        "event": event,
        "previous_hash": previous_hash,
        "result": result,
        "timestamp_utc": timestamp,
    }
    entry_hash = hashlib.sha256(json.dumps(entry_payload, sort_keys=True).encode("utf-8")).hexdigest()

    detail_lines = "\n".join(
        f"  {key}: {value}" for key, value in normalized_details.items()
    ) or "  details: none"
    block = (
        "=== Audit Entry ===\n"
        f"Timestamp (UTC): {timestamp}\n"
        f"Actor: {actor}\n"
        f"Event: {event}\n"
        f"Result: {result}\n"
        "Details:\n"
        f"{detail_lines}\n"
        f"Previous Hash: {previous_hash}\n"
        f"Entry Hash: {entry_hash}\n\n"
    )

    _set_read_only(target, enabled=False)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(block)
    harden_private_key_permissions(target)
    _set_read_only(target, enabled=True)
    return target


def log_signing_event(event: str, result: str = "success", **details: object) -> Path:
    return _append_audit_entry(SIGNING_AUDIT_LOG_PATH, "Signing Audit Log", event, result, **details)


def log_verification_event(event: str, result: str = "success", **details: object) -> Path:
    return _append_audit_entry(
        VERIFICATION_AUDIT_LOG_PATH,
        "Verification Audit Log",
        event,
        result,
        **details,
    )


def fingerprint_to_base64(fingerprint: bytes) -> str:
    return base64.b64encode(fingerprint).decode("ascii")


def fingerprint_from_base64(fingerprint_b64: str) -> bytes:
    return base64.b64decode(fingerprint_b64.encode("ascii"))


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_DIR / candidate).resolve()


def _load_registry_data() -> dict[str, object]:
    global _REGISTRY_CACHE_DATA, _REGISTRY_CACHE_MTIME_NS, _REGISTRY_DIMENSION_CACHE
    if _REGISTRY_STORAGE is not None:
        if _REGISTRY_CACHE_DATA is None:
            _REGISTRY_CACHE_DATA = _REGISTRY_STORAGE.load() or {"version": 1, "entries": []}
            _REGISTRY_DIMENSION_CACHE = {}
        return _REGISTRY_CACHE_DATA

    if not SIGNED_REGISTRY_PATH.exists():
        _REGISTRY_CACHE_DATA = {"version": 1, "entries": []}
        _REGISTRY_CACHE_MTIME_NS = None
        _REGISTRY_DIMENSION_CACHE = {}
        return {"version": 1, "entries": []}

    current_mtime_ns = SIGNED_REGISTRY_PATH.stat().st_mtime_ns
    if _REGISTRY_CACHE_DATA is not None and _REGISTRY_CACHE_MTIME_NS == current_mtime_ns:
        return _REGISTRY_CACHE_DATA

    _REGISTRY_CACHE_DATA = json.loads(SIGNED_REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    _REGISTRY_CACHE_MTIME_NS = current_mtime_ns
    _REGISTRY_DIMENSION_CACHE = {}
    return _REGISTRY_CACHE_DATA


def _write_registry_data(data: dict[str, object]) -> Path:
    global _REGISTRY_CACHE_DATA, _REGISTRY_CACHE_MTIME_NS, _REGISTRY_DIMENSION_CACHE
    if _REGISTRY_STORAGE is not None:
        _REGISTRY_STORAGE.save(data)
        _REGISTRY_CACHE_DATA = data
        _REGISTRY_DIMENSION_CACHE = {}
        return SIGNED_REGISTRY_PATH

    SIGNED_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _set_read_only(SIGNED_REGISTRY_PATH, enabled=False)
    SIGNED_REGISTRY_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    make_public_bundle_readable(SIGNED_REGISTRY_PATH)
    _set_read_only(SIGNED_REGISTRY_PATH, enabled=True)
    _REGISTRY_CACHE_DATA = data
    _REGISTRY_CACHE_MTIME_NS = SIGNED_REGISTRY_PATH.stat().st_mtime_ns
    _REGISTRY_DIMENSION_CACHE = {}
    return SIGNED_REGISTRY_PATH


def register_signed_asset(
    asset_type: str,
    output_path: str | Path,
    reference_fingerprint: bytes,
    signature_b64: str,
    source_path: str | Path | None = None,
    page_number: int | None = None,
    metadata: dict[str, object] | None = None,
) -> Path:
    data = _load_registry_data()
    entries = list(data.get("entries", []))
    output_str = str(resolve_project_path(output_path))

    filtered_entries = []
    for entry in entries:
        if entry.get("output_path") != output_str:
            filtered_entries.append(entry)
            continue
        if page_number is None and entry.get("asset_type") == asset_type and entry.get("page_number") is None:
            continue
        if page_number is not None and entry.get("asset_type") == asset_type and entry.get("page_number") == page_number:
            continue
        filtered_entries.append(entry)

    filtered_entries.append(
        {
            "asset_type": asset_type,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
            "output_path": output_str,
            "page_number": page_number,
            "reference_fingerprint_b64": fingerprint_to_base64(reference_fingerprint),
            "signature_b64": signature_b64,
            "source_path": str(resolve_project_path(source_path)) if source_path is not None else None,
        }
    )
    data["entries"] = filtered_entries
    return _write_registry_data(data)


def _distances_within_thresholds(
    distances: dict[str, int],
    *,
    max_total_distance: int,
    max_dhash_distance: int,
    max_phash_distance: int,
) -> bool:
    return (
        distances["total"] <= max_total_distance
        and distances["dhash"] <= max_dhash_distance
        and distances["phash"] <= max_phash_distance
    )


def registry_fingerprint_matches(
    reference_fingerprint: bytes,
    candidate_fingerprint: bytes,
) -> bool:
    distances = fingerprint_distance(reference_fingerprint, candidate_fingerprint)
    return _distances_within_thresholds(
        distances,
        max_total_distance=SCREENSHOT_REGISTRY_MAX_TOTAL_DISTANCE,
        max_dhash_distance=SCREENSHOT_REGISTRY_MAX_DHASH_DISTANCE,
        max_phash_distance=SCREENSHOT_REGISTRY_MAX_PHASH_DISTANCE,
    )


def registry_entry_output_dimensions(entry: dict[str, object]) -> tuple[int, int] | None:
    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        width = metadata.get("width")
        height = metadata.get("height")
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            return width, height

    output_path = entry.get("output_path")
    if not output_path:
        return None

    resolved_path = resolve_project_path(output_path)
    cache_key = str(resolved_path)
    if cache_key in _REGISTRY_DIMENSION_CACHE:
        return _REGISTRY_DIMENSION_CACHE[cache_key]

    if not resolved_path.exists():
        _REGISTRY_DIMENSION_CACHE[cache_key] = None
        return None

    image = cv2.imread(str(resolved_path), cv2.IMREAD_COLOR)
    if image is None:
        _REGISTRY_DIMENSION_CACHE[cache_key] = None
        return None
    height, width = image.shape[:2]
    dimensions = (width, height)
    _REGISTRY_DIMENSION_CACHE[cache_key] = dimensions
    return dimensions


def find_registry_matches(
    candidate_fingerprint: bytes,
    asset_types: tuple[str, ...] = ("image", "pdf_page"),
    *,
    max_total_distance: int,
    max_dhash_distance: int,
    max_phash_distance: int,
    require_output_dimensions: bool = False,
) -> list[dict[str, object]]:
    data = _load_registry_data()
    matches: list[dict[str, object]] = []

    for entry in data.get("entries", []):
        if entry.get("asset_type") not in asset_types:
            continue
        reference_fingerprint = fingerprint_from_base64(entry["reference_fingerprint_b64"])
        distances = fingerprint_distance(reference_fingerprint, candidate_fingerprint)
        if not _distances_within_thresholds(
            distances,
            max_total_distance=max_total_distance,
            max_dhash_distance=max_dhash_distance,
            max_phash_distance=max_phash_distance,
        ):
            continue

        dimensions = registry_entry_output_dimensions(entry)
        if require_output_dimensions and dimensions is None:
            continue

        matches.append(
            {
                "distance": distances,
                "dimensions": dimensions,
                "entry": entry,
            }
        )

    matches.sort(key=lambda match: str(match["entry"].get("created_at_utc", "")), reverse=True)
    matches.sort(
        key=lambda match: (
            0 if match["dimensions"] is not None else 1,
            match["distance"]["total"],
            match["distance"]["dhash"],
            match["distance"]["phash"],
        )
    )
    return matches


def find_registry_match(
    candidate_fingerprint: bytes,
    asset_types: tuple[str, ...] = ("image", "pdf_page"),
) -> tuple[dict[str, object] | None, dict[str, int] | None]:
    matches = find_registry_matches(
        candidate_fingerprint,
        asset_types=asset_types,
        max_total_distance=SCREENSHOT_REGISTRY_MAX_TOTAL_DISTANCE,
        max_dhash_distance=SCREENSHOT_REGISTRY_MAX_DHASH_DISTANCE,
        max_phash_distance=SCREENSHOT_REGISTRY_MAX_PHASH_DISTANCE,
        require_output_dimensions=False,
    )
    if not matches:
        return None, None
    return matches[0]["entry"], matches[0]["distance"]


def _bytes_to_blob(data: bytes) -> tuple[DATA_BLOB, object]:
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(
        cbData=len(data),
        pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def seal_private_key_bytes(private_key_bytes: bytes) -> bytes:
    if not is_windows():
        raise OSError("Windows DPAPI sealing is only available on Windows hosts.")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob, input_buffer = _bytes_to_blob(private_key_bytes)
    output_blob = DATA_BLOB()

    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        DPAPI_DESCRIPTION,
        None,
        None,
        None,
        0x01,
        ctypes.byref(output_blob),
    ):
        raise OSError(f"Failed to protect the private key with Windows DPAPI: {ctypes.GetLastError()}")

    try:
        protected_bytes = _blob_to_bytes(output_blob)
    finally:
        kernel32.LocalFree(output_blob.pbData)
        del input_buffer

    container = {
        "format": SEALED_KEY_FORMAT,
        "protection": "windows-dpapi-current-user",
        "description": DPAPI_DESCRIPTION,
        "ciphertext_b64": base64.b64encode(protected_bytes).decode("ascii"),
    }
    return json.dumps(container, indent=2, sort_keys=True).encode("utf-8")


def unseal_private_key_bytes(sealed_payload: bytes) -> bytes:
    if not is_windows():
        raise OSError("Windows DPAPI unsealing is only available on Windows hosts.")

    try:
        container = json.loads(sealed_payload.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Private key file is not a valid sealed key container.") from exc

    if container.get("format") != SEALED_KEY_FORMAT:
        raise ValueError("Unsupported sealed private key container format.")

    protected_bytes = base64.b64decode(container["ciphertext_b64"].encode("ascii"))

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob, input_buffer = _bytes_to_blob(protected_bytes)
    output_blob = DATA_BLOB()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x01,
        ctypes.byref(output_blob),
    ):
        raise OSError(
            "Failed to unprotect the private key. "
            "This sealed key can only be read by the Windows user that created it."
        )

    try:
        return _blob_to_bytes(output_blob)
    finally:
        kernel32.LocalFree(output_blob.pbData)
        del input_buffer


def is_plaintext_private_key(data: bytes) -> bool:
    return b"BEGIN RSA PRIVATE KEY" in data or b"BEGIN PRIVATE KEY" in data


def is_sealed_private_key(data: bytes) -> bool:
    try:
        container = json.loads(data.decode("utf-8"))
    except Exception:
        return False
    return container.get("format") == SEALED_KEY_FORMAT


def create_locked_backup_folder(private_key_path: str | Path | None = None) -> Path:
    target = Path(private_key_path) if private_key_path else PRIVATE_KEY_PATH
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = PRIVATE_KEY_BACKUP_ROOT / f"backup_{target.stem}_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    harden_private_key_permissions(PRIVATE_KEY_BACKUP_ROOT, is_directory=True)
    harden_private_key_permissions(backup_dir, is_directory=True)
    log_security_event("private_key_backup_folder_created", backup_dir=str(backup_dir))
    return backup_dir


def write_encrypted_private_key_file(path: str | Path, private_key_bytes: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    sealed_payload = seal_private_key_bytes(private_key_bytes)
    target.write_bytes(sealed_payload)
    harden_private_key_permissions(target)
    log_security_event("private_key_sealed", path=str(target), size=len(sealed_payload))

    backup_dir = create_locked_backup_folder(target)
    backup_path = backup_dir / target.name
    backup_path.write_bytes(sealed_payload)
    harden_private_key_permissions(backup_path)
    log_security_event("private_key_backup_written", backup_path=str(backup_path))
    return target


def harden_existing_private_key_file(private_key_path: str | Path | None = None) -> Path:
    path = Path(private_key_path) if private_key_path else PRIVATE_KEY_PATH
    if not path.exists():
        raise FileNotFoundError(f"Private key not found: {path}")

    raw_bytes = path.read_bytes()
    if is_sealed_private_key(raw_bytes):
        harden_private_key_permissions(path)
        harden_private_key_permissions(PRIVATE_KEY_BACKUP_ROOT, is_directory=True)
        log_security_event("private_key_permissions_reapplied", path=str(path))
        return path

    if not is_plaintext_private_key(raw_bytes):
        raise ValueError("Private key file is neither a plaintext PEM nor a sealed key container.")

    log_security_event("plaintext_private_key_detected", path=str(path))
    private_key = serialization.load_pem_private_key(raw_bytes, password=None)
    return save_private_key(private_key, path)


def read_image(image_path: str | Path) -> np.ndarray:
    """Load an image from disk and normalize it to 8-bit BGR."""
    path = Path(image_path)
    if path.suffix.lower() == ".png":
        return _read_image_with_pillow(path)

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is not None:
        return image

    return _read_image_with_pillow(path)


def _read_image_with_pillow(image_path: Path) -> np.ndarray:
    if not image_path.exists():
        raise FileNotFoundError(f"Could not read image: {image_path}")

    with Image.open(image_path) as pil_image:
        if pil_image.mode in {"RGBA", "LA"} or "transparency" in pil_image.info:
            rgba_image = pil_image.convert("RGBA")
            white_background = Image.new("RGBA", rgba_image.size, (255, 255, 255, 255))
            pil_image = Image.alpha_composite(white_background, rgba_image).convert("RGB")
        else:
            pil_image = pil_image.convert("RGB")

        rgb_image = np.array(pil_image, dtype=np.uint8)
        return cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)


def write_image(image_path: str | Path, image: np.ndarray) -> Path:
    """Persist an image using sensible defaults for PNG/JPEG outputs."""
    path = Path(image_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    params: list[int] = []
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        params = [cv2.IMWRITE_JPEG_QUALITY, 95]
    if not cv2.imwrite(str(path), image, params):
        raise RuntimeError(f"Failed to write image: {path}")
    return path


def crop_to_block_grid(image: np.ndarray, block_size: int = BLOCK_SIZE) -> np.ndarray:
    """Crop only the trailing edges so the image fits an exact DCT block grid."""
    height, width = image.shape[:2]
    usable_height = height - (height % block_size)
    usable_width = width - (width % block_size)
    if usable_height < block_size or usable_width < block_size:
        raise ValueError("Image is too small for watermark processing.")
    return image[:usable_height, :usable_width].copy()


def _dct_matrix(size: int = BLOCK_SIZE) -> np.ndarray:
    """Orthonormal DCT-II matrix, so that dct2(X) equals D @ X @ D.T."""
    frequencies = np.arange(size).reshape(-1, 1)
    positions = np.arange(size).reshape(1, -1)
    matrix = np.cos(np.pi * (2 * positions + 1) * frequencies / (2 * size)) * np.sqrt(2.0 / size)
    matrix[0] = np.sqrt(1.0 / size)
    return matrix.astype(np.float32)


DCT_MATRIX = _dct_matrix()


def image_to_blocks(luminance: np.ndarray) -> np.ndarray:
    """Reshape a luminance plane into a (rows, cols, 8, 8) stack of blocks."""
    height, width = luminance.shape
    return (
        luminance.reshape(height // BLOCK_SIZE, BLOCK_SIZE, width // BLOCK_SIZE, BLOCK_SIZE)
        .transpose(0, 2, 1, 3)
        .copy()
    )


def blocks_to_image(blocks: np.ndarray) -> np.ndarray:
    """Inverse of image_to_blocks."""
    rows, cols = blocks.shape[:2]
    return blocks.transpose(0, 2, 1, 3).reshape(rows * BLOCK_SIZE, cols * BLOCK_SIZE)


def canonicalize_image_for_hash(image: np.ndarray) -> np.ndarray:
    """
    Remove the watermark carrier coefficients before hashing.

    Signing happens before embedding, but verification sees the embedded image.
    By neutralizing every DCT coefficient pair reserved for watermark carriers
    in every 8x8 luminance block, the signer and verifier hash the same
    canonical visual content instead of two slightly different pixel layouts.

    Every block is transformed in one batched matrix product rather than a
    per-block call. A megapixel image holds around 17,000 blocks, and crossing
    into OpenCV once per block dominated the cost of every fingerprint. The
    transform is identical, so fingerprints are unchanged.
    """
    working_image = crop_to_block_grid(image)
    ycrcb = cv2.cvtColor(working_image, cv2.COLOR_BGR2YCrCb)
    luminance = ycrcb[:, :, 0].astype(np.float32)

    blocks = image_to_blocks(luminance)
    blocks -= 128.0
    coefficients = DCT_MATRIX @ blocks @ DCT_MATRIX.T

    for (a_row, a_col), (b_row, b_col) in WATERMARK_EMBED_COEFFICIENT_PAIRS:
        neutral_value = (
            coefficients[..., a_row, a_col] + coefficients[..., b_row, b_col]
        ) / 2.0
        coefficients[..., a_row, a_col] = neutral_value
        coefficients[..., b_row, b_col] = neutral_value

    restored = np.clip(DCT_MATRIX.T @ coefficients @ DCT_MATRIX + 128.0, 0, 255)

    ycrcb[:, :, 0] = blocks_to_image(restored).astype(np.uint8)
    return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)


def load_private_key(private_key_path: str | Path | None = None):
    path = Path(private_key_path) if private_key_path else PRIVATE_KEY_PATH
    with path.open("rb") as handle:
        raw_bytes = handle.read()

    if is_plaintext_private_key(raw_bytes):
        private_key = serialization.load_pem_private_key(raw_bytes, password=None)
        # Auto-migrate legacy plaintext keys into the sealed format the first time
        # they are loaded, so older projects become protected without manual steps.
        # Only the project's own root key qualifies: DPAPI does not exist off
        # Windows, and backend callers hand us short-lived key material that must
        # be read as-is rather than rewritten in place.
        if is_windows() and path == PRIVATE_KEY_PATH:
            log_security_event("legacy_plaintext_private_key_loaded", path=str(path))
            save_private_key(private_key, path)
        return private_key

    if not is_sealed_private_key(raw_bytes):
        raise ValueError("Private key file is not a supported sealed key container.")

    harden_private_key_permissions(path)
    private_key_bytes = unseal_private_key_bytes(raw_bytes)
    return serialization.load_pem_private_key(private_key_bytes, password=None)


def load_public_key(public_key_path: str | Path | None = None):
    path = Path(public_key_path) if public_key_path else PUBLIC_KEY_PATH
    with path.open("rb") as handle:
        return serialization.load_pem_public_key(handle.read())


def save_private_key(private_key, private_key_path: str | Path | None = None) -> Path:
    path = Path(private_key_path) if private_key_path else PRIVATE_KEY_PATH
    private_key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return write_encrypted_private_key_file(path, private_key_bytes)


def save_public_key(public_key, public_key_path: str | Path | None = None) -> Path:
    path = Path(public_key_path) if public_key_path else PUBLIC_KEY_PATH
    path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    make_public_bundle_readable(path)
    return path


def generate_image_hash(image: np.ndarray | str | Path) -> bytes:
    """
    Build a SHA256 digest from a compact perceptual fingerprint of the poster.

    The digest is derived from a canonicalized perceptual fingerprint instead of
    raw bytes. That lets the signer and verifier operate on the same robust
    visual identity even after watermark embedding or moderate recompression.
    """
    if isinstance(image, (str, Path)):
        image = read_image(image)

    return fingerprint_digest(generate_image_fingerprint(image))


def generate_image_fingerprint(image: np.ndarray | str | Path) -> bytes:
    """
    Generate a 128-bit perceptual fingerprint for the poster.

    We combine dHash and pHash style features so the verifier can tolerate mild
    compression noise across a wide variety of images while still reacting
    strongly to visible content edits.
    """
    if isinstance(image, (str, Path)):
        image = read_image(image)

    image = canonicalize_image_for_hash(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dhash_bits = _difference_hash_bits(gray)
    phash_bits = _perceptual_hash_bits(gray)
    combined_bits = np.concatenate([dhash_bits, phash_bits]).astype(np.uint8)
    fingerprint = np.packbits(combined_bits).tobytes()
    if len(fingerprint) != REFERENCE_FINGERPRINT_BYTES:
        raise ValueError("Unexpected fingerprint length.")
    return fingerprint


def generate_fast_image_fingerprint(image: np.ndarray | str | Path) -> bytes:
    """
    Generate the same perceptual fingerprint without full DCT neutralization.

    Screenshot recovery only needs a quick registry shortlist before the
    embedded watermark is checked cryptographically, so this avoids scanning
    every 8x8 block in large phone screenshots.
    """
    if isinstance(image, (str, Path)):
        image = read_image(image)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dhash_bits = _difference_hash_bits(gray)
    phash_bits = _perceptual_hash_bits(gray)
    combined_bits = np.concatenate([dhash_bits, phash_bits]).astype(np.uint8)
    fingerprint = np.packbits(combined_bits).tobytes()
    if len(fingerprint) != REFERENCE_FINGERPRINT_BYTES:
        raise ValueError("Unexpected fingerprint length.")
    return fingerprint


def fingerprint_digest(fingerprint: bytes) -> bytes:
    return hashlib.sha256(fingerprint).digest()


def fingerprint_matches(reference_fingerprint: bytes, candidate_fingerprint: bytes) -> bool:
    distances = fingerprint_distance(reference_fingerprint, candidate_fingerprint)
    return (
        distances["total"] <= MAX_TOTAL_FINGERPRINT_DISTANCE
        and distances["dhash"] <= MAX_DHASH_DISTANCE
        and distances["phash"] <= MAX_PHASH_DISTANCE
    )


def fingerprint_distance(reference_fingerprint: bytes, candidate_fingerprint: bytes) -> dict[str, int]:
    if len(reference_fingerprint) != REFERENCE_FINGERPRINT_BYTES:
        raise ValueError("Reference fingerprint length is invalid.")
    if len(candidate_fingerprint) != REFERENCE_FINGERPRINT_BYTES:
        raise ValueError("Candidate fingerprint length is invalid.")

    reference_bits = np.unpackbits(np.frombuffer(reference_fingerprint, dtype=np.uint8))
    candidate_bits = np.unpackbits(np.frombuffer(candidate_fingerprint, dtype=np.uint8))

    dhash_distance = int(np.count_nonzero(reference_bits[:DHASH_BITS] != candidate_bits[:DHASH_BITS]))
    phash_distance = int(
        np.count_nonzero(reference_bits[DHASH_BITS:] != candidate_bits[DHASH_BITS:])
    )
    return {
        "dhash": dhash_distance,
        "phash": phash_distance,
        "total": dhash_distance + phash_distance,
    }


def _difference_hash_bits(gray_image: np.ndarray, width: int = 9, height: int = 8) -> np.ndarray:
    small = cv2.resize(gray_image, (width, height), interpolation=cv2.INTER_AREA)
    return (small[:, 1:] > small[:, :-1]).astype(np.uint8).flatten()


def _perceptual_hash_bits(gray_image: np.ndarray, size: int = 32, low: int = 8) -> np.ndarray:
    small = cv2.resize(gray_image, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct_view = cv2.dct(small)[:low, :low]
    median = np.median(dct_view[1:, :].flatten())
    return (dct_view > median).astype(np.uint8).flatten()


def sign_digest(private_key, digest: bytes) -> bytes:
    """Sign a precomputed SHA256 digest using RSA-PSS."""
    return private_key.sign(
        digest,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        asym_utils.Prehashed(hashes.SHA256()),
    )


def verify_digest_signature(public_key, digest: bytes, signature: bytes) -> bool:
    """Validate an RSA-PSS signature over a precomputed SHA256 digest."""
    try:
        public_key.verify(
            signature,
            digest,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            asym_utils.Prehashed(hashes.SHA256()),
        )
        return True
    except Exception:
        return False


def signature_to_base64(signature: bytes) -> str:
    return base64.b64encode(signature).decode("ascii")


def signature_from_base64(signature_b64: str) -> bytes:
    return base64.b64decode(signature_b64.encode("ascii"))


def build_watermark_payload(signature: bytes, fingerprint: bytes) -> bytes:
    if len(signature) != RSA_SIGNATURE_BYTES:
        raise ValueError(
            f"Expected a {RSA_SIGNATURE_BYTES}-byte RSA signature, got {len(signature)} bytes."
        )
    if len(fingerprint) != REFERENCE_FINGERPRINT_BYTES:
        raise ValueError(
            f"Expected a {REFERENCE_FINGERPRINT_BYTES}-byte reference fingerprint, "
            f"got {len(fingerprint)} bytes."
        )

    body = (
        bytes([PAYLOAD_VERSION, len(fingerprint)])
        + struct.pack(">H", len(signature))
        + fingerprint
        + signature
    )
    checksum = hashlib.sha256(body).digest()[:WATERMARK_CHECKSUM_BYTES]
    return WATERMARK_MAGIC + checksum + body


def parse_watermark_payload(payload: bytes) -> tuple[bytes, bytes]:
    minimum_bytes = len(WATERMARK_MAGIC) + WATERMARK_CHECKSUM_BYTES + 1 + 1 + 2
    if len(payload) < minimum_bytes:
        raise ValueError("Watermark payload is too short.")

    if payload[: len(WATERMARK_MAGIC)] != WATERMARK_MAGIC:
        raise ValueError("Watermark marker not found.")

    checksum = payload[4:8]
    body = payload[8:]
    expected_checksum = hashlib.sha256(body).digest()[:WATERMARK_CHECKSUM_BYTES]
    if checksum != expected_checksum:
        raise ValueError("Watermark checksum mismatch.")

    version = body[0]
    if version != PAYLOAD_VERSION:
        raise ValueError(f"Unsupported watermark payload version: {version}")

    fingerprint_length = body[1]
    signature_length = struct.unpack(">H", body[2:4])[0]
    fingerprint_start = 4
    fingerprint_end = fingerprint_start + fingerprint_length
    signature_start = fingerprint_end
    signature_end = signature_start + signature_length

    fingerprint = body[fingerprint_start:fingerprint_end]
    signature = body[signature_start:signature_end]
    if len(fingerprint) != fingerprint_length:
        raise ValueError("Watermark fingerprint is truncated.")
    if len(signature) != signature_length:
        raise ValueError("Watermark payload is truncated.")
    if len(fingerprint) != REFERENCE_FINGERPRINT_BYTES:
        raise ValueError("Recovered fingerprint length does not match the expected size.")

    return fingerprint, signature


def bytes_to_bits(payload: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(payload, dtype=np.uint8))


def bits_to_bytes(bits: Iterable[int]) -> bytes:
    bit_array = np.array(list(bits), dtype=np.uint8)
    if bit_array.size % 8 != 0:
        raise ValueError("Bit stream length must be divisible by 8.")
    return np.packbits(bit_array).tobytes()


def watermark_payload_bit_length() -> int:
    return len(
        build_watermark_payload(
            b"\x00" * RSA_SIGNATURE_BYTES,
            b"\x00" * REFERENCE_FINGERPRINT_BYTES,
        )
    ) * 8


def watermark_repetition(total_blocks: int, payload_bits: int) -> int:
    """Use the largest odd repetition count that fits in the image capacity."""
    repetition = min(MAX_REPETITION, total_blocks // payload_bits)
    if repetition > 1 and repetition % 2 == 0:
        repetition -= 1
    return max(1, repetition)


def legacy_watermark_permutation(total_blocks: int) -> np.ndarray:
    rng = np.random.default_rng(WATERMARK_SHUFFLE_SEED)
    return rng.permutation(total_blocks)


def watermark_permutation(total_blocks: int) -> np.ndarray:
    """
    Return a deterministic block order that can be reproduced outside Python.

    The original prototype used NumPy's generator permutation, which is awkward
    to match exactly on Android. New signed images use a SHA-256 sorted order so
    both desktop and mobile verifiers can derive the same permutation.
    """
    keyed_indices = []
    for index in range(total_blocks):
        key = hashlib.sha256(
            struct.pack(">II", WATERMARK_SHUFFLE_SEED, index)
        ).digest()
        keyed_indices.append((key, index))
    keyed_indices.sort(key=lambda item: item[0])
    return np.array([index for _, index in keyed_indices], dtype=np.int64)


def block_coordinates(block_index: int, blocks_per_row: int, block_size: int = BLOCK_SIZE) -> tuple[int, int]:
    row = (block_index // blocks_per_row) * block_size
    col = (block_index % blocks_per_row) * block_size
    return row, col
