"""Public endpoints for the RazorpayX payout advice demonstration.

Open, like the citizen verifier, and for the same reason: a vendor deciding
whether to load a lorry has no RazorpayX account and should not need one. The
whole point is that checking is free and instant for the person carrying the
risk.

There is no endpoint that produces a forged advice. Recall is measured by the
offline benchmark, which builds forgeries in-process and never writes one to a
public path.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

# The signing engine and the razorpayx package both live at the repository
# root. The adapter normally puts that on the path, but this router must not
# depend on another module having been imported first.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import settings
from ..security import require_admin
from ..services.audit_service import AuditService
from ..services.document_store import get_document_store
from ..services.firebase_service import FirebaseService

router = APIRouter(prefix="/api/payout-advice", tags=["payout-advice"])

# The demo signs with its own key pair, kept beside the runtime data so it
# survives a redeploy on a mounted disk. It is deliberately not an operator's
# authority key: this endpoint is open, and nothing reachable without
# authentication should be able to sign with a real authority's key.
_DEMO_DIR = settings.local_upload_root / "payout_demo"


def _keys() -> tuple[Path, Path]:
    _DEMO_DIR.mkdir(parents=True, exist_ok=True)
    private, public = _DEMO_DIR / "priv.pem", _DEMO_DIR / "pub.pem"
    if not private.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        public.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))
    return private, public


#: Modes RazorpayX settles by. NEFT and RTGS are the ones that matter here:
#: they settle in batches rather than instantly, which is the window an edited
#: advice is used in.
_MODES = ("NEFT", "RTGS", "IMPS", "UPI")


#: The issuing authority these advices are attributed to.
#:
#: A constant rather than an operator's authority, because these are signed
#: with the demo key pair rather than anybody's real key. Recording them under
#: a name of their own keeps them out of an authority's record while still
#: letting them be listed, attributed and downloaded like any other document.
_RZP_AUTHORITY_ID = "razorpayx_payouts"
_RZP_AUTHORITY_NAME = "RazorpayX Payouts"


def _record_issued(issued, advice, caller: dict) -> str | None:
    """File an issued advice as a signed document, so the console can see it.

    Without this the advice exists only on the container's disk: invisible to
    the Documents tab, to an account's page under People, and to the download
    route, which reads the object store rather than that directory. It was
    signed by the system on somebody's behalf, so it is recorded the same way
    anything else signed here is.

    Never allowed to fail the request. The advice has already been rendered
    and signed by this point, and losing the bookkeeping is worth less than
    losing the document.
    """
    try:
        source = Path(issued.image_path)
        document_id = f"rzp_{issued.payout_id}"
        storage_path = f"signed_documents/{_RZP_AUTHORITY_ID}/{document_id}/{source.name}"
        get_document_store().put(source, storage_path)

        FirebaseService().create_document("signed_documents", document_id, {
            "document_id": document_id,
            "authority_id": _RZP_AUTHORITY_ID,
            "authority_name": _RZP_AUTHORITY_NAME,
            "original_filename": f"{issued.payout_id}.png",
            "signed_filename": source.name,
            "file_type": "PNG",
            "storage_type": get_document_store().name,
            "signed_file_storage_path": storage_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "signature_status": "signed",
            "status": "SIGNED",
            "signed_by_uid": caller.get("uid"),
            "signed_by_email": caller.get("email"),
            "signing_mode": "invisible_watermark",
            "payout_id": issued.payout_id,
            "amount": advice.amount_text,
            "mode": advice.mode,
            "notes": "Payout advice issued and signed by RazorpayX.",
        })

        AuditService().record(
            "DOCUMENT_SIGNED",
            actor=caller.get("email") or "system",
            actor_uid=caller.get("uid"),
            authority_id=_RZP_AUTHORITY_ID,
            document_id=document_id,
        )
        return document_id
    except Exception as exc:  # pragma: no cover - bookkeeping must not block
        print(f"WARNING: issued advice {issued.payout_id} was not recorded: {exc}", flush=True)
        return None


@router.post("/issue")
async def issue_advice(
    seed: int | None = Form(None),
    amount: str | None = Form(None),
    beneficiary: str | None = Form(None),
    mode: str | None = Form(None),
    caller: dict = Depends(require_admin),
):
    """Issue one signed advice and return what was printed on it.

    Everything not supplied is filled from a seeded sample, so the caller can
    name only the amount and still get a complete, plausible document. The
    amount arrives in rupees because that is what someone types; it is held in
    paise because binary floating point cannot represent 8,03,626.45 and an
    advice whose printed total disagrees with its own record by a hundredth of
    a rupee would be reported as a forgery by its own field check.
    """
    from razorpayx.advice import sample_advice
    from razorpayx.issue import issue

    try:
        chosen = seed if seed is not None else random.randrange(1, 10_000_000)
        private, public = _keys()
        advice = sample_advice(random.Random(chosen))

        changes: dict[str, object] = {}

        if amount is not None and amount.strip():
            cleaned = amount.replace(",", "").replace("₹", "").strip()
            try:
                paise = int(round(Decimal(cleaned) * 100))
            except (InvalidOperation, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Enter the amount as a number, for example 803626.45",
                ) from exc
            if paise <= 0:
                raise HTTPException(status_code=400, detail="The amount must be more than zero.")
            # The hero amount is printed at 52pt in a fixed box. Past about a
            # crore the digits run into the margin and the reader samples a
            # clipped glyph, which is a false accusation waiting to happen.
            if paise > 99_99_99_999_99:
                raise HTTPException(
                    status_code=400,
                    detail="This demo prints amounts up to 99,99,99,999.99.",
                )
            changes["amount_paise"] = paise

        if beneficiary is not None and beneficiary.strip():
            name = " ".join(beneficiary.split())[:38]
            changes["beneficiary_legal"] = name
            changes["beneficiary"] = name

        if mode is not None and mode.strip():
            picked = mode.strip().upper()
            if picked not in _MODES:
                raise HTTPException(status_code=400, detail=f"Mode must be one of {', '.join(_MODES)}.")
            changes["mode"] = picked

        if changes:
            advice = advice.replace(**changes)

        issued = issue(advice, _DEMO_DIR / "issued",
                       private_key=private, public_key=public, seed=chosen)
        document_id = _record_issued(issued, advice, caller)
        return {
            "payout_id": issued.payout_id,
            "amount": advice.amount_text,
            "mode": advice.mode,
            "beneficiary": advice.beneficiary_legal,
            "utr": advice.utr,
            "printed": issued.printed,
            "image_url": f"/api/payout-advice/image/{issued.payout_id}",
            # Present when the advice was filed. The console downloads through
            # the ordinary document route so the per-account rule applies to
            # these exactly as it does to everything else.
            "document_id": document_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/image/{payout_id}")
async def advice_image(payout_id: str):
    """Serve one issued specimen.

    The id is matched against the issued directory rather than joined onto it,
    so a caller cannot walk out of the directory with a crafted id.
    """
    safe = "".join(ch for ch in payout_id if ch.isalnum() or ch == "_")
    path = _DEMO_DIR / "issued" / f"{safe}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No such advice.")
    return FileResponse(path, media_type="image/png",
                        filename=f"{safe}.png")


@router.post("/verify")
async def verify_advice(
    file: UploadFile = File(...),
    payout_id: str = Form(...),
):
    """Check an uploaded advice against the record kept when it was issued."""
    import tempfile

    from utils import read_image

    from razorpayx.check import check
    from razorpayx.issue import load_record

    safe = "".join(ch for ch in payout_id if ch.isalnum() or ch == "_")
    record_path = _DEMO_DIR / "issued" / f"{safe}.json"
    if not record_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="No advice was issued with that payout id in this demo.",
        )

    suffix = Path(file.filename or "upload.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="Upload a PNG or JPEG.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(await file.read())
        upload = Path(handle.name)

    try:
        record = load_record(record_path)
        _, public = _keys()
        verdict = check(read_image(upload), upload, record.printed,
                        public.read_text(encoding="utf-8"))
        return {
            "status": verdict.status,
            "headline": verdict.headline,
            "detail": verdict.detail,
            "watermark_ok": verdict.watermark_ok,
            "fields": [
                {
                    "name": f.name,
                    "expected": f.expected,
                    "read": f.read,
                    "matched": f.matched,
                    "confidence": round(f.confidence, 3),
                }
                for f in verdict.findings
            ],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        upload.unlink(missing_ok=True)
