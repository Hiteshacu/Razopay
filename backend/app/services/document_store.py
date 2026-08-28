from __future__ import annotations

import mimetypes
import re
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from ..config import settings


class DocumentNotFound(Exception):
    """The store has no object under that key."""


class DocumentStore(ABC):
    """Where signed documents live.

    Signing does not care which implementation it is talking to, so a
    deployment can move between a laptop and any object store without the
    engine noticing. Keys are store-relative paths such as
    ``signed_documents/<authority>/<document_id>/signed_output.png``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier recorded on the document, for diagnostics."""

    @abstractmethod
    def put(self, local_path: Path, key: str) -> None:
        """Copy a local file into the store under ``key``."""

    @abstractmethod
    def stream(self, key: str) -> Iterator[bytes]:
        """Yield the object's bytes, raising DocumentNotFound if absent."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object. A missing object is not an error."""

    @staticmethod
    def content_type_for(key: str) -> str:
        return mimetypes.guess_type(key)[0] or "application/octet-stream"


class LocalDocumentStore(DocumentStore):
    """Files on the machine's own disk.

    Correct for development. On a host without a persistent disk — a free
    Render instance — anything written here is lost on the next restart, so
    this is not a deployment option there.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.local_upload_root)

    @property
    def name(self) -> str:
        return "local"

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        # The key is influenced by an uploaded filename, so a store that can
        # be walked out of with ".." is worth closing off.
        if root != candidate and root not in candidate.parents:
            raise ValueError(f"Refusing to resolve a key outside the store root: {key}")
        return candidate

    def put(self, local_path: Path, key: str) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = Path(local_path).resolve()
        if source == target:
            return  # the engine already wrote it in place
        target.write_bytes(source.read_bytes())

    def stream(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise DocumentNotFound(key)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


class S3DocumentStore(DocumentStore):
    """Any S3-compatible object store: Backblaze B2, Cloudflare R2, AWS, MinIO.

    Deliberately written against S3 rather than Backblaze's own API. The S3
    dialect is the one thing every object store agrees on, so changing
    provider is a change of endpoint rather than a rewrite — which is worth
    more than the dependency it costs, because the provider is the part most
    likely to change.
    """

    # Backblaze puts the region in the endpoint host
    # (s3.us-west-004.backblazeb2.com); boto3 insists on being told one.
    _REGION_IN_HOST = re.compile(r"^s3\.([a-z0-9-]+)\.backblazeb2\.com$", re.I)

    def __init__(self) -> None:
        endpoint = settings.s3_endpoint_url.strip()
        if not endpoint:
            raise RuntimeError("DOCUMENT_STORE=s3 needs S3_ENDPOINT_URL to be set.")
        if not settings.s3_bucket:
            raise RuntimeError("DOCUMENT_STORE=s3 needs S3_BUCKET to be set.")
        if not (settings.s3_access_key_id and settings.s3_secret_access_key):
            raise RuntimeError(
                "DOCUMENT_STORE=s3 needs S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY."
            )

        self.endpoint = endpoint if "://" in endpoint else f"https://{endpoint}"
        self.bucket = settings.s3_bucket
        self.region = settings.s3_region or self._region_from_endpoint(self.endpoint)
        self._client = None
        # uvicorn runs sync handlers on a thread pool, and boto3 client
        # construction is not documented as thread-safe.
        self._lock = threading.Lock()

    @classmethod
    def _region_from_endpoint(cls, endpoint: str) -> str:
        host = endpoint.split("://", 1)[-1].split("/", 1)[0]
        match = cls._REGION_IN_HOST.match(host)
        return match.group(1) if match else "us-east-1"

    @property
    def name(self) -> str:
        return "s3"

    @property
    def client(self):
        """Built on first use.

        Constructing this at import time would turn a wrong credential into a
        startup crash rather than a failed request, and on Render a startup
        crash takes the whole service down instead of one endpoint.
        """
        if self._client is None:
            with self._lock:
                if self._client is None:
                    import boto3
                    from botocore.config import Config

                    self._client = boto3.client(
                        "s3",
                        endpoint_url=self.endpoint,
                        region_name=self.region,
                        aws_access_key_id=settings.s3_access_key_id,
                        aws_secret_access_key=settings.s3_secret_access_key,
                        config=Config(
                            signature_version="s3v4",
                            retries={"max_attempts": 3, "mode": "standard"},
                            connect_timeout=10,
                            read_timeout=60,
                        ),
                    )
        return self._client

    def put(self, local_path: Path, key: str) -> None:
        with Path(local_path).open("rb") as handle:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=handle,
                ContentType=self.content_type_for(key),
            )

    def stream(self, key: str) -> Iterator[bytes]:
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}:
                raise DocumentNotFound(key) from exc
            raise
        body = response["Body"]
        try:
            while True:
                chunk = body.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    def delete(self, key: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError:
            pass


_STORE: DocumentStore | None = None
_STORE_LOCK = threading.Lock()


def get_document_store() -> DocumentStore:
    """The store this deployment is configured to use."""
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                backend = settings.document_store_backend
                _STORE = S3DocumentStore() if backend == "s3" else LocalDocumentStore()
    return _STORE


def reset_document_store() -> None:
    """Drop the cached store. For tests and for the reset script."""
    global _STORE
    with _STORE_LOCK:
        _STORE = None
