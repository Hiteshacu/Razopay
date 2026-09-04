"""Issue and check RazorpayX Payroll payslips.

The same two halves as the payout advice, for a document with a worse gap
behind it. An advice is checked by somebody who was sent it. A payslip is
checked by a lender, a landlord or a background-verification firm, none of
whom have any channel to the payroll system: Account Aggregator carries data
from regulated financial institutions and a private employer is not one, so an
employer-issued payslip cannot travel that route even in principle.

Issuing requires a caller, because what it signs is filed against an account.
Checking does not, and must not — the party who needs to know whether a salary
is real is exactly the party with no account here.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import settings
from ..security import require_admin
from ..services.audit_service import AuditService
from ..services.document_store import get_document_store
from ..services.firebase_service import FirebaseService

router = APIRouter(prefix="/api/payslip", tags=["payslip"])

# Its own key pair, beside the runtime data. Not an operator's authority key:
# these are signed on RazorpayX Payroll's behalf, not on any one operator's.
_SLIP_DIR = settings.local_upload_root / "payslip_demo"

_AUTHORITY_ID = "razorpayx_payroll"
_AUTHORITY_NAME = "RazorpayX Payroll"


def _keys() -> tuple[Path, Path]:
    _SLIP_DIR.mkdir(parents=True, exist_ok=True)
    private, public = _SLIP_DIR / "priv.pem", _SLIP_DIR / "pub.pem"
    if not private.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        public.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))
    return private, public


def _paise(value: str, field: str) -> int:
    """Rupees as typed, into paise.

    Held in paise because binary floating point cannot represent 53,387.10,
    and a payslip whose printed total disagreed with its own record by a
    hundredth of a rupee would be reported as forged by its own field check.
    """
    cleaned = value.replace(",", "").replace("₹", "").strip()
    try:
        paise = int(round(Decimal(cleaned) * 100))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Enter {field} as a number, for example 53387.10",
        ) from exc
    if paise <= 0:
        raise HTTPException(status_code=400, detail=f"{field} must be more than zero.")
    # The hero sits in a fixed box at 52pt. Digits that run into the margin
    # are read clipped, and a clipped 8 is a 3 — a false accusation waiting.
    if paise > 99_99_99_999_99:
        raise HTTPException(status_code=400, detail="This demo prints up to 99,99,99,999.99.")
    return paise


def _record_issued(issued, slip, caller: dict) -> str | None:
    """File a payslip as a signed document, so the console can see it.

    Never allowed to fail the request: the payslip has been rendered and
    signed by this point, and losing the bookkeeping is worth less than losing
    the document.
    """
    try:
        source = Path(issued.image_path)
        # The slip id already begins with "slip_", so prefixing again produced
        # slip_slip_9AJ122EWKVPR5Y. Used as-is: it is already unique and
        # already says what it is.
        document_id = issued.payout_id
        storage_path = f"signed_documents/{_AUTHORITY_ID}/{document_id}/{source.name}"
        store = get_document_store()
        store.put(source, storage_path)

        FirebaseService().create_document("signed_documents", document_id, {
            "document_id": document_id,
            "authority_id": _AUTHORITY_ID,
            "authority_name": _AUTHORITY_NAME,
            "original_filename": f"{issued.payout_id}.png",
            "signed_filename": source.name,
            "file_type": "PNG",
            "storage_type": store.name,
            "signed_file_storage_path": storage_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "signature_status": "signed",
            "status": "SIGNED",
            "signed_by_uid": caller.get("uid"),
            "signed_by_email": caller.get("email"),
            "signing_mode": "invisible_watermark",
            "slip_id": issued.payout_id,
            "employee": slip.employee,
            "period": slip.period,
            "net_pay": slip.net_text,
            "notes": "Payslip issued and signed by RazorpayX Payroll.",
        })

        AuditService().record(
            "DOCUMENT_SIGNED",
            actor=caller.get("email") or "system",
            actor_uid=caller.get("uid"),
            authority_id=_AUTHORITY_ID,
            document_id=document_id,
        )
        return document_id
    except Exception as exc:  # pragma: no cover - bookkeeping must not block
        print(f"WARNING: payslip {issued.payout_id} was not recorded: {exc}", flush=True)
        return None


@router.post("/issue")
async def issue_payslip_route(
    employee: str = Form(...),
    net: str | None = Form(None),
    period: str | None = Form(None),
    employer: str | None = Form(None),
    seed: int | None = Form(None),
    caller: dict = Depends(require_admin),
):
    """Issue one signed payslip and return what was printed on it.

    Only the employee name is required. Everything else is filled from a
    seeded sample, because a half-filled payslip is not a fair test of a
    reader that has to find every field — and because the name is the thing
    that ties the document to the person presenting it.

    `net` sets take-home pay, and the earnings are solved backwards from it so
    the page stays arithmetically consistent. A payslip whose gross minus
    deductions does not equal its net is caught by any human who looks, which
    would make the field check look better than it is.
    """
    from razorpayx.issue import issue_payslip
    from razorpayx.payslip import sample_payslip

    try:
        chosen = seed if seed is not None else random.randrange(1, 10_000_000)
        private, public = _keys()
        slip = sample_payslip(random.Random(chosen))

        changes: dict[str, object] = {"employee": " ".join(employee.split())[:34]}

        if net is not None and net.strip():
            target = _paise(net, "net pay")
            # Gross is basic + 40% HRA + 15% allowance = 1.55 of basic.
            # Deductions are 12% PF + 8% tax = 0.20. Net is therefore 1.35 of
            # basic, so basic is the target over 1.35. Solved rather than
            # asserted: the first version divided by 1.15 and every payslip
            # printed a net around 17% above the one that was asked for, which
            # the field check could not catch because the record agreed with
            # the page. Both were wrong together.
            basic = int(round(target / 1.35))
            changes.update(
                basic_paise=basic,
                hra_paise=int(basic * 0.40),
                allowance_paise=int(basic * 0.15),
                pf_paise=int(basic * 0.12),
                tax_paise=int(basic * 0.08),
            )

        if period is not None and period.strip():
            changes["period"] = " ".join(period.split())[:24]
        if employer is not None and employer.strip():
            changes["employer"] = " ".join(employer.split())[:38]

        slip = slip.replace(**changes)
        issued = issue_payslip(slip, _SLIP_DIR / "issued",
                               private_key=private, public_key=public, seed=chosen)
        document_id = _record_issued(issued, slip, caller)
        return {
            "slip_id": issued.payout_id,
            "employee": slip.employee,
            "employee_id": slip.employee_id,
            "period": slip.period,
            "employer": slip.employer,
            "net": slip.net_text,
            "gross": slip.gross_text,
            "deductions": slip.deductions_text,
            "printed": issued.printed,
            "image_url": f"/api/payslip/image/{issued.payout_id}",
            "document_id": document_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/image/{slip_id}")
async def payslip_image(slip_id: str):
    """Serve one issued payslip.

    The id is matched against the issued directory rather than joined onto it,
    so a caller cannot walk out of the directory with a crafted id.
    """
    safe = "".join(ch for ch in slip_id if ch.isalnum() or ch == "_")
    path = _SLIP_DIR / "issued" / f"{safe}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No such payslip.")
    return FileResponse(path, media_type="image/png", filename=f"{safe}.png")


def _check_from_signature(upload: Path, public_pem: Path, label: str) -> dict:
    """Decide from the proof in the pixels, and nothing else.

    No record is consulted, and none is needed. The signature says whether
    RazorpayX issued this page; the carrier woven through it says whether the
    page was edited afterwards and where. Both are read out of the file in
    hand, so a document issued a year ago on a service that has been redeployed
    since is answered exactly as well as one issued a minute ago.

    Comparing printed values against a stored record is the other way to do
    this, and it was how this endpoint worked. It reads more precisely — it can
    name the field and quote both values — but it is only as durable as the
    record, and it makes verification a question about a database rather than
    about the document. A reader holding a suspicious page should not be told
    "no advice was issued with that id" because a deploy erased a file.
    """
    from utils import read_image

    from razorpayx.locate import inspect_carrier
    from verify_poster import verify_poster

    image = read_image(upload)
    finding = inspect_carrier(image)

    # Every torn patch, not just the largest. A forger who changes two figures
    # leaves two, and showing one of them tells the reader the page is wrong
    # while pointing away from half of what is wrong with it.
    regions = [
        {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom,
         "blocks": r.blocks}
        for r in finding.regions
    ]

    try:
        outcome = verify_poster(upload, public_key_path=public_pem, audit=False)
        signed_ok = outcome[0] if isinstance(outcome, tuple) else bool(outcome)
        engine_message = ""
    except Exception as exc:
        signed_ok, engine_message = False, str(exc).lower()

    # Boxes are in the coordinates the carrier was read at, which is not the
    # uploaded size when recovery succeeded at another scale — so those
    # dimensions travel with them rather than the upload's.
    height, width = image.shape[:2]
    base = {
        "image_width": int(finding.read_width or width),
        "image_height": int(finding.read_height or height),
        "measurable": finding.measurable,
        "blob": finding.blob,
        "regions": regions,
    }

    # The carrier is torn in one place: an edit the page fingerprint's
    # tolerance is wide enough to absorb, which is the case it is blind to.
    if finding.edited:
        return {**base, "status": "ALTERED",
                "headline": f"Issued by RazorpayX, then edited",
                "detail": (f"The signature is real — RazorpayX did issue this {label}. "
                           "But the proof woven through the page is torn in one "
                           "region, which means that part was changed afterwards. "
                           "Do not release goods against this document.")}

    if signed_ok:
        return {**base, "status": "GENUINE", "headline": "Genuine",
                "detail": (f"RazorpayX issued this {label}, and the proof woven "
                           "through the page is intact everywhere. Note that NEFT "
                           "and RTGS settle in batches, so the credit may not have "
                           "reached the account yet.")}

    if "fingerprint" in engine_message:
        return {**base, "status": "ALTERED", "headline": "Issued by RazorpayX, then edited",
                "detail": (f"The signature is real — RazorpayX did issue this {label} "
                           "— but the page no longer matches what was signed.")}

    return {**base, "status": "NOT_ISSUED", "headline": "No RazorpayX signature found",
            "detail": (f"This image carries no embedded proof. RazorpayX did not "
                       f"issue this {label}, or it has been damaged past recovery: "
                       "a heavy crop, or a photograph of a screen.")}


@router.post("/verify")
async def verify_payslip(
    file: UploadFile = File(...),
    slip_id: str | None = Form(None),
):
    """Check an uploaded payslip from its signature alone.

    The id is accepted and ignored. It was required when the answer came from
    comparing against a stored record; it is kept so an older client does not
    break, and so a reader who has one is not told their input is invalid.
    """
    import tempfile

    suffix = Path(file.filename or "upload.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="Upload a PNG or JPEG.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(await file.read())
        upload = Path(handle.name)

    try:
        _, public = _keys()
        return _check_from_signature(upload, public, "payslip")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        upload.unlink(missing_ok=True)
