from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


_load_dotenv(BACKEND_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    firebase_credentials: str = os.getenv("FIREBASE_CREDENTIALS", "secrets/serviceAccountKey.json")
    use_local_storage: bool = _env_bool("USE_LOCAL_STORAGE", True)
    local_upload_dir: str = os.getenv("LOCAL_UPLOAD_DIR", "uploads")
    secure_keys_dir: str = os.getenv("SECURE_KEYS_DIR", "secure_private_keys")
    # "local" keeps state on disk; "firestore" is for hosts without durable
    # storage, such as a free Render instance.
    registry_backend: str = os.getenv("REGISTRY_BACKEND", "local").strip().lower()
    key_store_backend: str = os.getenv("KEY_STORE_BACKEND", "local").strip().lower()
    # Origin used to build download links for signed files. Render injects
    # RENDER_EXTERNAL_URL automatically, so a deployed instance stops handing
    # out localhost URLs that only resolve on the machine that signed.
    public_base_url: str = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or "http://127.0.0.1:8000"
    ).rstrip("/")
    firebase_storage_bucket: str = os.getenv("FIREBASE_STORAGE_BUCKET", "")
    # Where signed documents are kept. "local" is disk, correct for a laptop
    # and wrong for any host without a persistent disk. "s3" is any
    # S3-compatible store — Backblaze B2, Cloudflare R2, AWS, MinIO — chosen
    # over a provider's own API so that changing provider is a change of
    # endpoint rather than a rewrite.
    document_store_backend: str = os.getenv("DOCUMENT_STORE", "local").strip().lower()
    s3_endpoint_url: str = os.getenv("S3_ENDPOINT_URL", "").strip()
    s3_bucket: str = os.getenv("S3_BUCKET", "").strip()
    s3_region: str = os.getenv("S3_REGION", "").strip()
    s3_access_key_id: str = os.getenv("S3_ACCESS_KEY_ID", "").strip()
    s3_secret_access_key: str = os.getenv("S3_SECRET_ACCESS_KEY", "").strip()
    master_key: str = os.getenv("MASTER_KEY", "")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")
    # Turn on once Firebase Auth is configured and a first admin has signed
    # in. While false, the admin endpoints stay open — do not leave it that
    # way on a public deployment.
    require_admin_auth: bool = _env_bool("REQUIRE_ADMIN_AUTH", False)
    # Seed accounts: these emails are approved the first time they sign in,
    # so the first operator does not need an existing admin to let them in.
    admin_emails: tuple[str, ...] = tuple(
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    )
    # The one account that always administers the system. It is approved on
    # sight, cannot be demoted, and is where approval requests are sent.
    owner_email: str = os.getenv("OWNER_EMAIL", "").strip().lower()
    # Where approval requests are sent. Falls back to the owner.
    approval_notify_email: str = os.getenv("APPROVAL_NOTIFY_EMAIL", "").strip()
    # Accounts approved on sight as ordinary members.
    #
    # Separate from ADMIN_EMAILS on purpose. A shared demo account has to work
    # without anybody being awake to approve it, but seeding it through
    # ADMIN_EMAILS would also make it an administrator — and an account whose
    # password ships to every visitor must not be able to approve other
    # accounts. This grants exactly one thing: the ability to sign in and use
    # the console as a member.
    demo_emails: tuple[str, ...] = tuple(
        item.strip().lower()
        for item in os.getenv("DEMO_EMAILS", "").split(",")
        if item.strip()
    )
    # Origin of the portal, used to build the link in the approval email.
    portal_base_url: str = os.getenv("PORTAL_BASE_URL", "http://localhost:5173").rstrip("/")

    # --- Mail API over HTTPS (preferred) ---
    # Hosts commonly block the SMTP ports outright, so a mail API reached over
    # 443 is the transport that works everywhere. Takes priority over SMTP.
    resend_api_key: str = os.getenv("RESEND_API_KEY", "").strip()
    resend_from: str = os.getenv("RESEND_FROM", "onboarding@resend.dev").strip()

    # --- SMTP: fallback, only usable where the ports are open ---
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "").strip()
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    )
    storage_make_public: bool = os.getenv("STORAGE_MAKE_PUBLIC", "true").lower() == "true"
    storage_signed_url_minutes: int = int(os.getenv("STORAGE_SIGNED_URL_MINUTES", "1440"))
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    @property
    def credentials_path(self) -> Path:
        candidate = Path(self.firebase_credentials)
        return candidate if candidate.is_absolute() else BACKEND_ROOT / candidate

    @property
    def local_upload_root(self) -> Path:
        candidate = Path(self.local_upload_dir)
        return candidate if candidate.is_absolute() else BACKEND_ROOT / candidate

    @property
    def secure_keys_root(self) -> Path:
        candidate = Path(self.secure_keys_dir)
        return candidate if candidate.is_absolute() else BACKEND_ROOT / candidate

    @property
    def original_documents_dir(self) -> Path:
        return self.local_upload_root / "original_documents"

    @property
    def signed_documents_dir(self) -> Path:
        return self.local_upload_root / "signed_documents"

    @property
    def temp_dir(self) -> Path:
        return self.local_upload_root / "temp"

    @property
    def storage_mode(self) -> str:
        """Where signed documents are kept.

        Not use_local_storage, which now only governs the unused Firebase
        Storage path — reporting that would tell an operator the opposite of
        the truth about where their documents are.
        """
        return self.document_store_backend


settings = Settings()


def ensure_local_storage_dirs() -> None:
    directories = (
        settings.local_upload_root,
        settings.signed_documents_dir,
        settings.original_documents_dir,
        settings.temp_dir,
    )
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Could not create local storage directory '{directory}': {exc}") from exc
