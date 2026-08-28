from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..security import can_see_all_records
from ..security import require_admin
from ..services.document_store import DocumentNotFound, get_document_store
from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/documents", tags=["documents"])


def _signed_by(document: dict, caller: dict) -> bool:
    return bool(document.get("signed_by_uid")) and document.get("signed_by_uid") == caller.get("uid")


def _may_download(document: dict, caller: dict) -> bool:
    """Whether this caller may fetch this file.

    Wider than what the Documents tab lists: the owner may download any
    document, because the whole point of an account's page under People is
    to open the work it holds. Everyone else is held to their own.
    """
    if can_see_all_records(caller.get("role", "member")):
        return True
    return _signed_by(document, caller)


@router.get("")
def list_documents(
    authority_id: str | None = Query(default=None),
    admin: dict = Depends(require_admin),
):
    """The caller's own signed documents.

    Own only, for every account including the owner. The owner used to see
    every account's documents in this one list, which made it impossible to
    tell at a glance which were theirs. Another account's documents are
    reached through that account's page under People.
    """
    documents = FirebaseService().list_signed_documents(authority_id=authority_id)
    return [document for document in documents if _signed_by(document, admin)]


@router.get("/{document_id}/file")
def download_document(document_id: str, admin: dict = Depends(require_admin)):
    """The signed file itself, streamed through this backend.

    Downloads deliberately do not go straight to the object store. Routing
    them here is what makes the per-account rule real — a store URL, once
    issued, is a bearer token that anybody who receives it can replay, and
    the store has no idea who signed what.

    A document the caller may not see returns 404 rather than 403. 403 would
    confirm that the id exists, which is enough to enumerate other
    authorities' documents by guessing.
    """
    document = FirebaseService().get_document("signed_documents", document_id)
    if not document or not _may_download(document, admin):
        raise HTTPException(status_code=404, detail="No such document.")

    key = document.get("signed_file_storage_path")
    if not key:
        raise HTTPException(status_code=404, detail="This document has no stored file.")

    store = get_document_store()
    try:
        chunks = store.stream(key)
        # Pull the first chunk here so a missing object fails as a clean 404
        # rather than as a response that has already begun and then breaks.
        first = next(chunks, b"")
    except DocumentNotFound:
        raise HTTPException(
            status_code=404,
            detail="The signed file is no longer in storage.",
        ) from None

    def body():
        yield first
        yield from chunks

    filename = str(document.get("signed_filename") or f"{document_id}.png")
    # Header values must be latin-1; a generated filename should already be
    # safe, but a stray character should not take the download down with it.
    ascii_name = filename.encode("ascii", "ignore").decode() or f"{document_id}.png"

    return StreamingResponse(
        body(),
        media_type=store.content_type_for(key),
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"',
            # These are one-per-document and immutable once signed.
            "Cache-Control": "private, max-age=3600",
        },
    )
