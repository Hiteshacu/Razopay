from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import ensure_local_storage_dirs, settings
from ..core.trust_shield_adapter import verify_file_adapter
from .audit_service import utc_now
from .firebase_service import FirebaseService


class VerificationService:
    def __init__(self, firebase: FirebaseService | None = None) -> None:
        self.firebase = firebase or FirebaseService()
        ensure_local_storage_dirs()
        self.upload_dir = settings.temp_dir

    def _classify_error(self, exc: Exception) -> tuple[str, str]:
        """Turn an engine failure into one of the four verdicts.

        Order matters. Every "recovered, but ..." message the engine raises
        also contains the word "watermark", so the specific verdicts have to
        be tested before the generic nothing-was-found rules or they are
        swallowed by them.

        This previously matched on the words "signature" and "fingerprint",
        neither of which appears in the engine's actual wrong-key message
        ("...the selected public key did not validate it"). That fell through
        to ERROR, and because the automatic retry across other keys fires only
        on SIGNATURE_INVALID, it never fired — for exactly the case it exists
        to handle. Several other real messages fell through too: "Failed to
        extract watermark payload", "Forwarded-image recovery could not find
        a matching signed image geometry", "Poster is too small to contain a
        valid watermark".

        Kept deliberately in step with trustshield.api._classify in the
        library, so the same document gets the same verdict either way.
        """
        message = str(exc) or exc.__class__.__name__
        lowered = message.lower()

        if "did not validate" in lowered:
            return "SIGNATURE_INVALID", "The hidden proof was found, but the RSA signature was invalid."

        if "fingerprint did not match" in lowered or "content did not match" in lowered:
            return "TAMPERED", "The hidden signature does not match the current visual content."

        if "length does not match" in lowered or "length is invalid" in lowered:
            return "WATERMARK_NOT_FOUND", "No complete Digital Trust Shield proof could be recovered."

        if (
            "watermark" in lowered
            or "recovery could not" in lowered
            or "time budget" in lowered
            or "timed out" in lowered
        ):
            return "WATERMARK_NOT_FOUND", "No hidden Digital Trust Shield proof was found in this image."

        return "ERROR", message

    @staticmethod
    def _inspect_carrier(upload_path: Path) -> dict | None:
        """What the carrier says about this page, on its own.

        Read from the signature alone — the payload is recovered from the
        image in hand, so nothing is compared against any stored record.

        This catches what the fingerprint cannot. The fingerprint is 128 bits
        of whole-page structure and the tolerance that carries it through a
        messaging app also absorbs a repainted figure: a measured 4.1% edit
        passed as authentic on one page and was caught on another, because
        size is not what decides. The carrier is per-block, so an edit shows
        as a contiguous patch of flattened blocks where recompression shows as
        thin scatter.

        Never allowed to fail a verification.
        """
        try:
            import sys as _sys

            root = str(Path(__file__).resolve().parents[3])
            if root not in _sys.path:
                _sys.path.insert(0, root)
            from razorpayx.locate import EDIT_BLOB_THRESHOLD, inspect_carrier

            from utils import read_image

            finding = inspect_carrier(read_image(upload_path))
            payload = {
                "measurable": finding.measurable,
                "edited": finding.edited,
                "blob": finding.blob,
                "threshold": EDIT_BLOB_THRESHOLD,
                "background_rate": round(finding.background_rate, 4),
            }
            payload["read_width"] = finding.read_width
            payload["read_height"] = finding.read_height
            payload["page_wide"] = finding.page_wide
            payload["coverage"] = round(finding.coverage, 4)
            # Carried so the branch that reaches this through an exception can
            # still find the copy filed at signing time. It is not sent on to
            # the browser; the caller strips it.
            payload["signature"] = finding.signature
            payload["regions"] = [
                {"left": r.left, "top": r.top, "right": r.right,
                 "bottom": r.bottom, "blocks": r.blocks}
                for r in finding.regions
            ]
            return payload
        except Exception as exc:
            # Never fail a verification over this, but never swallow it
            # silently either: this returning None looks exactly like a page
            # with nothing wrong, and the only difference visible from outside
            # is that no region is ever drawn.
            print(f"WARNING: carrier inspection failed for {upload_path.name}: {exc}", flush=True)
            return None

    @staticmethod
    def _reference_pages(filed: bytes, matched_page: int | None, page) -> list:
        """The page of the filed copy that this upload is a copy of.

        A signed PDF is the case this exists for. Its bytes are not an image,
        so decoding them as one returns nothing and the comparison silently
        never ran — which is how a page exported from a signed circular came
        back as a document that was never signed.

        Which page matters as much as which document. A reader uploads one
        page and nothing in the image says which; compared against the wrong
        one, every line differs and the answer is a page covered in boxes. The
        page is chosen by perceptual fingerprint rather than by comparing
        against each in turn, because a fingerprint is a few milliseconds and a
        comparison is most of a second.
        """
        import tempfile

        import cv2
        import numpy as np

        if not filed.startswith(b"%PDF"):
            decoded = cv2.imdecode(np.frombuffer(filed, dtype=np.uint8), cv2.IMREAD_COLOR)
            return [decoded] if decoded is not None else []

        from pdf_support import render_pdf_pages
        from utils import generate_image_fingerprint

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            handle.write(filed)
            pdf_path = Path(handle.name)
        try:
            pages = render_pdf_pages(pdf_path)
        finally:
            pdf_path.unlink(missing_ok=True)
        if not pages:
            return []
        if matched_page is not None and 0 <= matched_page < len(pages):
            return [pages[matched_page]]
        if len(pages) == 1:
            return pages

        wanted = generate_image_fingerprint(page)
        best, best_distance = pages[0], None
        for candidate in pages:
            other = generate_image_fingerprint(candidate)
            distance = sum(bin(a ^ b).count("1") for a, b in zip(wanted, other))
            if best_distance is None or distance < best_distance:
                best, best_distance = candidate, distance
        return [best]

    @staticmethod
    def _page_fingerprint(upload_path: Path) -> str:
        """The 128-bit perceptual fingerprint of a page, as hex.

        The same function the signing flow stored, so the two are comparable.
        """
        try:
            import sys as _sys

            root = str(Path(__file__).resolve().parents[3])
            if root not in _sys.path:
                _sys.path.insert(0, root)
            from ..core.trust_shield_adapter import visual_fingerprint_hex

            return visual_fingerprint_hex(upload_path)
        except Exception:
            return ""

    def _compare_to_filed_copy(self, upload_path: Path, signature_b64: str | None) -> dict | None:
        """What the copy filed at signing time says about the page in hand.

        This is the answer the carrier cannot give. A page that has been
        through an online image editor has had every line of text erased and
        redrawn, so the carrier is broken along all of them and cannot say
        which line a forger also changed — both are new pixels. Content can
        say, but only against something, and the something is the copy the
        object store kept when the document was signed.

        Returns None whenever there is nothing to compare against, which is
        not a failure: a document signed before the signature was recorded, a
        record whose file has been deleted, or an image carrying no signature
        at all. The carrier still answers in every one of those cases.

        Never allowed to fail a verification.
        """
        try:
            import sys as _sys

            root = str(Path(__file__).resolve().parents[3])
            if root not in _sys.path:
                _sys.path.insert(0, root)

            record = self.firebase.find_signed_document_by_signature(signature_b64)
            if not record:
                # No signature, or none that names a filed record. That is the
                # ordinary state of a page an image editor has been through, and
                # it is exactly the page most in need of this comparison — so
                # fall back to finding the document by what it looks like. This
                # only identifies which document is being looked at; whether
                # this copy is genuine is still the signature's question, and
                # the caller says so where the signature is gone.
                fingerprint = self._page_fingerprint(upload_path)
                record = self.firebase.find_signed_document_by_fingerprint(fingerprint)
            if not record:
                return None
            storage_path = record.get("signed_file_storage_path")
            if not storage_path:
                return None

            from .document_store import get_document_store

            chunks = get_document_store().stream(str(storage_path))
            first = next(chunks, b"")
            if not first:
                return None
            filed = first + b"".join(chunks)

            import cv2
            import numpy as np

            from razorpayx.compare import compare
            from utils import read_image

            page = read_image(upload_path)
            references = self._reference_pages(filed, record.get("matched_page"), page)
            if not references:
                return None

            # One page, or the best of several. A reader who exports page two
            # of a signed circular and edits it uploads one page, and nothing
            # in that image says which page it was — so when the fingerprint
            # match did not already name one, every page is tried and the one
            # that disagrees least is the one being looked at. A wrong page
            # disagrees almost everywhere, so this is not a close call.
            finding = None
            for candidate in references:
                attempt = compare(page, candidate)
                if not attempt.comparable:
                    continue
                if finding is None or attempt.coverage < finding.coverage:
                    finding = attempt
            if finding is None:
                return None
            return {
                "compared": True,
                "identified_by": "signature" if signature_b64 and record.get(
                    "fingerprint_distance") is None else "appearance",
                "differs": finding.differs,
                "coverage": round(finding.coverage, 4),
                "image_width": finding.width,
                "image_height": finding.height,
                "document_id": record.get("document_id"),
                "regions": [
                    {"left": r.left, "top": r.top, "right": r.right,
                     "bottom": r.bottom, "blocks": r.blocks}
                    for r in finding.regions
                ],
            }
        except Exception as exc:  # pragma: no cover - never blocks a verdict
            print(f"WARNING: comparison against the filed copy failed for "
                  f"{upload_path.name}: {exc}", flush=True)
            return None

    def _verify_with_public_key(
        self,
        upload_path: Path,
        key_id: str,
        key: dict,
        selected_key_id: str | None = None,
    ) -> dict:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as key_file:
            key_file.write(str(key["public_key_pem"]).encode("utf-8"))
            public_key_path = Path(key_file.name)
        try:
            result = verify_file_adapter(upload_path, public_key_path)
            carrier = self._inspect_carrier(upload_path)
            content = self._compare_to_filed_copy(upload_path, result.get("signature"))
            # Used, not shown: 344 characters of base64 in every response, to
            # tell a reader something the image already carries.
            if carrier:
                carrier.pop("signature", None)
            if result["valid"]:
                details = dict(result.get("details", {}))
                if carrier:
                    details["carrier"] = carrier
                if content:
                    details["content"] = content
                if selected_key_id and selected_key_id != key_id:
                    details = {
                        **details,
                        "auto_detected_key": True,
                        "selected_key_id": selected_key_id,
                    }

                # The signature is genuine and the fingerprint still matches,
                # but the carrier is flattened somewhere. That is an edit small
                # enough for the fingerprint's tolerance to absorb, which is
                # exactly the case it was blind to, so the carrier overrules.
                # The filed copy has the last word when there is one. It
                # answers the question the reader is actually asking — has
                # anything this page says changed — where the carrier answers
                # a narrower one, whether any pixel was repainted. On a page an
                # editor re-typeset those give opposite answers, and the filed
                # copy is the one that is right.
                if content and content.get("compared"):
                    if content.get("differs"):
                        count = len(content.get("regions") or ())
                        where = "in one place" if count == 1 else f"in {count} places"
                        return {
                            "success": False,
                            "result": "TAMPERED",
                            "reason": (
                                "This page does not say what it said when it was "
                                f"signed. Compared against the copy filed then, it "
                                f"differs {where}, marked on the image."
                            ),
                            "authority_name": key.get("authority_name"),
                            "authority_id": key.get("authority_id"),
                            "key_id": key_id,
                            "details": details,
                        }
                    if carrier and carrier.get("edited"):
                        return {
                            "success": True,
                            "result": "AUTHENTIC",
                            "reason": (
                                "Every word and figure on this page matches the copy "
                                "filed when it was signed. The file itself has been "
                                "re-saved since — an image editor redraws the text it "
                                "finds — so it is not the original file, but nothing "
                                "it says has been changed."
                            ),
                            "authority_name": key.get("authority_name"),
                            "authority_id": key.get("authority_id"),
                            "key_id": key_id,
                            "details": details,
                        }

                if carrier and carrier.get("edited"):
                    count = len(carrier.get("regions") or ())
                    where = "in one region" if count <= 1 else f"in {count} separate regions"
                    if carrier.get("page_wide"):
                        share = round(float(carrier.get("coverage") or 0) * 100)
                        note = (
                            "The signature is genuine, but the proof is broken across "
                            f"{share}% of the page rather than in one place. An online "
                            "image editor does that: it redraws every line of text it "
                            "finds, so all of them become new pixels. Whatever else was "
                            "changed cannot be told apart from the editor's own work — "
                            "ask for the original file."
                        )
                    else:
                        note = (
                            "The signature is genuine, but the proof woven through "
                            f"the page is broken {where} — those parts were edited "
                            "after signing."
                        )
                    return {
                        "success": False,
                        "result": "TAMPERED",
                        "reason": note,
                        "authority_name": key.get("authority_name"),
                        "authority_id": key.get("authority_id"),
                        "key_id": key_id,
                        "details": details,
                    }
                return {
                    "success": True,
                    "result": "AUTHENTIC",
                    "reason": "Embedded signature verified and visual fingerprint matched.",
                    "authority_name": key.get("authority_name"),
                    "authority_id": key.get("authority_id"),
                    "key_id": key_id,
                    "details": details,
                }
            # The page changed. Say where, from the carrier rather than from
            # any record of what was printed — there is nothing to compare
            # against here, and that is the point: the signature travels with
            # the document and a stored record does not.
            tampered_details = dict(result.get("details", {}))
            if carrier:
                tampered_details["carrier"] = carrier
            return {
                "success": False,
                "result": "TAMPERED",
                "reason": "The document proof was present but did not validate.",
                "authority_name": key.get("authority_name"),
                "authority_id": key.get("authority_id"),
                "key_id": key_id,
                "details": tampered_details,
            }
        except Exception as exc:
            result_code, reason = self._classify_error(exc)
            details: dict = {"technical_error": str(exc)}

            # The engine raises rather than returns on a fingerprint mismatch,
            # so a page edited enough to break the whole-page fingerprint lands
            # here — and this branch used to say TAMPERED and show the reader
            # nothing, no region and no box, on exactly the documents where
            # where matters most. The carrier is worth asking only for that
            # verdict: TAMPERED means the payload was recovered and checked, so
            # there is a carrier to reason about. WATERMARK_NOT_FOUND means
            # there is not, and asking costs a full read at a dozen scales to
            # be told what is already known.
            # A page an image editor has re-typeset carries no readable
            # signature at all, so it lands here as WATERMARK_NOT_FOUND — a
            # verdict that tells the holder of a genuine document it was never
            # issued. The filed copy can still be found by what the page looks
            # like, and it is the only thing that can say whether any of what
            # the page says has changed.
            if result_code == "WATERMARK_NOT_FOUND":
                content = self._compare_to_filed_copy(upload_path, None)
                if content and content.get("compared"):
                    details["content"] = content
                    document = content.get("document_id")
                    if content.get("differs"):
                        count = len(content.get("regions") or ())
                        where = "in one place" if count == 1 else f"in {count} places"
                        return {
                            "success": False,
                            "result": "TAMPERED",
                            "reason": (
                                "No signature survives in this file — it has been "
                                "re-saved, which destroys the proof woven through the "
                                f"pixels. It is recognisably document {document}, and "
                                f"against the copy filed then it differs {where}, "
                                "marked on the image."
                            ),
                            "authority_name": key.get("authority_name"),
                            "authority_id": key.get("authority_id"),
                            "key_id": key_id,
                            "details": details,
                        }
                    return {
                        "success": False,
                        "result": "WATERMARK_NOT_FOUND",
                        "reason": (
                            "No signature survives in this file — it has been re-saved, "
                            "which destroys the proof woven through the pixels, so this "
                            f"copy cannot be proved genuine. It is recognisably document "
                            f"{document}, and every word and figure on it matches the "
                            "copy filed when that was signed. Ask for the original file "
                            "before relying on it."
                        ),
                        "authority_name": key.get("authority_name"),
                        "authority_id": key.get("authority_id"),
                        "key_id": key_id,
                        "details": details,
                    }

            if result_code == "TAMPERED":
                carrier = self._inspect_carrier(upload_path)
                if carrier:
                    details["carrier"] = carrier
                    content = self._compare_to_filed_copy(
                        upload_path, carrier.pop("signature", None))
                    if content:
                        details["content"] = content
                        if content.get("differs"):
                            count = len(content.get("regions") or ())
                            where = "in one place" if count == 1 else f"in {count} places"
                            details["carrier"] = carrier
                            return {
                                "success": False,
                                "result": "TAMPERED",
                                "reason": (
                                    "This page does not say what it said when it was "
                                    f"signed. Compared against the copy filed then, it "
                                    f"differs {where}, marked on the image."
                                ),
                                "authority_name": key.get("authority_name"),
                                "authority_id": key.get("authority_id"),
                                "key_id": key_id,
                                "details": details,
                            }
                    count = len(carrier.get("regions") or ())
                    if carrier.get("page_wide"):
                        share = round(float(carrier.get("coverage") or 0) * 100)
                        reason = (
                            "The document was signed, but the proof is broken across "
                            f"{share}% of the page rather than in one place — the mark of "
                            "an online image editor, which redraws every line of text it "
                            "finds. Ask for the original file."
                        )
                    elif count:
                        where = "in one region" if count == 1 else f"in {count} separate regions"
                        reason = (
                            "The document was signed, but the page no longer matches "
                            f"what was signed — the proof woven through it is broken {where}, "
                            "shown on the image."
                        )

            return {
                "success": False,
                "result": result_code,
                "reason": reason,
                "authority_name": key.get("authority_name"),
                "authority_id": key.get("authority_id"),
                "key_id": key_id,
                "details": details,
            }
        finally:
            public_key_path.unlink(missing_ok=True)

    # Trying every key against an image that carries no proof at all multiplies
    # the slowest path by the number of registered keys. Cap it even when a
    # retry is warranted.
    MAX_KEY_RETRIES = 3

    def _active_public_keys_for_retry(self, selected_key_id: str) -> list[dict]:
        return [
            key
            for key in self.firebase.list_public_keys()
            if key.get("active", True) and key.get("key_id") != selected_key_id
        ][: self.MAX_KEY_RETRIES]

    @staticmethod
    def _is_worth_retrying_with_other_keys(result: str) -> bool:
        """Only a key mismatch is worth re-testing against other keys.

        SIGNATURE_INVALID means a watermark was recovered but the selected key
        did not validate it — exactly the case where the document belongs to a
        different authority, so another key may succeed.

        WATERMARK_NOT_FOUND means no proof was recovered at all, and TAMPERED
        means one was recovered and validated but the visible content has since
        changed. Neither verdict can be altered by trying a different key, so
        retrying only repeats the most expensive path once per registered key.
        """
        return result == "SIGNATURE_INVALID"

    async def verify_upload(self, file: UploadFile, key_id: str) -> dict:
        key = self.firebase.get_document("public_keys", key_id)
        if not key:
            raise ValueError(f"Public key not found: {key_id}")

        verification_id = f"ver_{uuid4().hex[:16]}"
        filename = Path(file.filename or "verification_upload.png").name
        suffix = Path(filename).suffix.lower() or ".png"
        upload_path = self.upload_dir / f"{verification_id}{suffix}"

        with upload_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        try:
            response = self._verify_with_public_key(upload_path, key_id, key)

            if not response["success"] and self._is_worth_retrying_with_other_keys(response["result"]):
                for candidate_key in self._active_public_keys_for_retry(key_id):
                    candidate_key_id = str(candidate_key.get("key_id"))
                    candidate_response = self._verify_with_public_key(
                        upload_path,
                        candidate_key_id,
                        candidate_key,
                        selected_key_id=key_id,
                    )
                    if candidate_response["success"]:
                        response = candidate_response
                        break

            log_data = {
                "verification_id": verification_id,
                "uploaded_filename": filename,
                "selected_key_id": key_id,
                "authority_id": response.get("authority_id") or key.get("authority_id"),
                "result": response["result"],
                "reason": response["reason"],
                "confidence_or_distance": response["details"].get("distance") if response.get("details") else None,
                "verified_at": utc_now(),
                "uploaded_file_storage_path_optional": None,
            }
            self.firebase.add_auto_document("verification_logs", log_data)
            return response
        finally:
            try:
                upload_path.unlink(missing_ok=True)
            except Exception:
                pass
