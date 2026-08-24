from __future__ import annotations

import json
import mimetypes
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

from generate_keys import generate_keys
from sign_poster import sign_poster
from utils import PRIVATE_KEY_PATH, PUBLIC_KEY_PATH
from verify_poster import verify_poster
from video_support import is_supported_video_path


HOST = "127.0.0.1"
PORT = 5000
PROJECT_DIR = Path(__file__).resolve().parent
DEMO_RUNTIME_DIR = PROJECT_DIR / "demo_runtime"
UPLOADS_DIR = DEMO_RUNTIME_DIR / "uploads"
SIGNED_DIR = DEMO_RUNTIME_DIR / "signed"
VERIFY_DIR = DEMO_RUNTIME_DIR / "verify"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS
STATIC_ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/demo": "demo.html",
    "/demo.html": "demo.html",
    "/styles.css": "styles.css",
    "/script.js": "script.js",
    "/demo.js": "demo.js",
}


def ensure_runtime_dirs() -> None:
    for directory in (UPLOADS_DIR, SIGNED_DIR, VERIFY_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def keys_available() -> bool:
    return PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists()


def allowed_upload(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS


def is_video_upload(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_VIDEO_EXTENSIONS


def build_storage_name(original_name: str) -> str:
    suffix = Path(original_name).suffix.lower() or ".png"
    safe_stem = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in Path(original_name).stem
    ).strip("_")
    safe_stem = safe_stem or "payment_screenshot"
    return f"{safe_stem}_{uuid4().hex}{suffix}"


def save_uploaded_blob(target_directory: Path, filename: str, content: bytes) -> Path:
    ensure_runtime_dirs()
    destination = target_directory / build_storage_name(filename)
    destination.write_bytes(content)
    return destination


def parse_multipart_form(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    synthetic_message = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    message = BytesParser(policy=default).parsebytes(synthetic_message)
    if not message.is_multipart():
        raise ValueError("Expected multipart form data.")

    fields: dict[str, str] = {}
    files: dict[str, dict[str, object]] = {}

    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue

        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[field_name] = {
                "filename": filename,
                "content": payload,
                "content_type": part.get_content_type(),
            }
        else:
            charset = part.get_content_charset() or "utf-8"
            fields[field_name] = payload.decode(charset, errors="replace")

    return fields, files


class DemoRequestHandler(BaseHTTPRequestHandler):
    server_version = "DigitalTrustShieldDemo/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in STATIC_ROUTES:
            self._serve_static(PROJECT_DIR / STATIC_ROUTES[path])
            return

        if path == "/api/status":
            self._json_response(
                200,
                {
                    "ok": True,
                    "hasKeys": keys_available(),
                    "privateKeyReady": PRIVATE_KEY_PATH.exists(),
                    "publicKeyReady": PUBLIC_KEY_PATH.exists(),
                },
            )
            return

        if path.startswith("/api/download/"):
            filename = unquote(path.removeprefix("/api/download/"))
            target = SIGNED_DIR / Path(filename).name
            if not target.exists():
                self._json_response(404, {"ok": False, "message": "Signed file not found."})
                return

            self._serve_file(target, as_attachment=True)
            return

        self._json_response(404, {"ok": False, "message": "Route not found."})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/generate-keys":
            self._handle_generate_keys()
            return

        if path == "/api/sign":
            self._handle_sign()
            return

        if path == "/api/verify":
            self._handle_verify()
            return

        self._json_response(404, {"ok": False, "message": "Route not found."})

    def _handle_generate_keys(self) -> None:
        try:
            private_path, public_path = generate_keys()
        except Exception as exc:
            self._json_response(500, {"ok": False, "message": f"RSA key generation failed: {exc}"})
            return

        self._json_response(
            200,
            {
                "ok": True,
                "message": "RSA key pair generated successfully. You can now sign a screenshot or video.",
                "privateKeyPath": private_path,
                "publicKeyPath": public_path,
            },
        )

    def _handle_sign(self) -> None:
        if not keys_available():
            self._json_response(
                400,
                {"ok": False, "message": "Generate the RSA key pair first before signing an image or video."},
            )
            return

        try:
            _, files = self._read_form_data()
        except Exception as exc:
            self._json_response(400, {"ok": False, "message": f"Invalid upload request: {exc}"})
            return

        uploaded_file = files.get("file")
        if uploaded_file is None:
            self._json_response(400, {"ok": False, "message": "Please upload a payment screenshot or video to sign."})
            return

        filename = str(uploaded_file["filename"])
        if not allowed_upload(filename):
            self._json_response(
                400,
                {
                    "ok": False,
                    "message": "Only PNG, JPG, JPEG, MP4, MOV, AVI, MKV, and M4V files are supported in this demo.",
                },
            )
            return

        upload_path = save_uploaded_blob(UPLOADS_DIR, filename, bytes(uploaded_file["content"]))
        if is_video_upload(filename):
            signed_path = SIGNED_DIR / f"{upload_path.stem}_signed.mp4"
        else:
            signed_path = SIGNED_DIR / f"{upload_path.stem}_signed{upload_path.suffix.lower()}"

        try:
            signature_b64, output_path = sign_poster(
                upload_path,
                output_path=signed_path,
                self_check=True,
            )
        except Exception as exc:
            self._json_response(500, {"ok": False, "message": f"Digital signing failed: {exc}"})
            return

        if isinstance(signature_b64, list):
            self._json_response(400, {"ok": False, "message": "This demo currently supports image signing only."})
            return

        if isinstance(signature_b64, dict):
            signature_preview = (
                f"{signature_b64['signatures'][0][:24]}..."
                if signature_b64["signatures"]
                else "No signature preview available."
            )
            audio_message = (
                "Original audio was preserved."
                if signature_b64["audioPreserved"]
                else "Signed output currently contains the protected visual track only."
            )
            self._json_response(
                200,
                {
                    "ok": True,
                    "assetType": "video",
                    "message": "Video digitally signed successfully.",
                    "detail": (
                        f"Protected {signature_b64['sampledMoments']} timeline moments. {audio_message}"
                    ),
                    "downloadUrl": f"/api/download/{Path(output_path).name}",
                    "signedFilename": Path(output_path).name,
                    "signaturePreview": signature_preview,
                    "sampledMoments": signature_b64["sampledMoments"],
                    "audioPreserved": signature_b64["audioPreserved"],
                },
            )
            return

        self._json_response(
            200,
            {
                "ok": True,
                "assetType": "image",
                "message": "Payment screenshot digitally signed successfully.",
                "downloadUrl": f"/api/download/{Path(output_path).name}",
                "signedFilename": Path(output_path).name,
                "signaturePreview": f"{signature_b64[:24]}...",
            },
        )

    def _handle_verify(self) -> None:
        if not PUBLIC_KEY_PATH.exists():
            self._json_response(
                400,
                {
                    "ok": False,
                    "message": "Generate the RSA key pair first so the verifier has a public key.",
                },
            )
            return

        try:
            _, files = self._read_form_data()
        except Exception as exc:
            self._json_response(400, {"ok": False, "message": f"Invalid upload request: {exc}"})
            return

        uploaded_file = files.get("file")
        if uploaded_file is None:
            self._json_response(400, {"ok": False, "message": "Please upload an image or video to verify."})
            return

        filename = str(uploaded_file["filename"])
        if not allowed_upload(filename):
            self._json_response(
                400,
                {
                    "ok": False,
                    "message": "Only PNG, JPG, JPEG, MP4, MOV, AVI, MKV, and M4V files are supported in this demo.",
                },
            )
            return

        verify_path = save_uploaded_blob(VERIFY_DIR, filename, bytes(uploaded_file["content"]))

        try:
            verification_result = verify_poster(verify_path, audit=False)
        except Exception as exc:
            self._json_response(
                200,
                {
                    "ok": True,
                    "assetType": "video" if is_supported_video_path(filename) else "image",
                    "isAuthentic": False,
                    "status": "Unsigned/Unverified video" if is_supported_video_path(filename) else "AI/Tampered image",
                    "detail": str(exc),
                },
            )
            return

        if isinstance(verification_result, dict):
            self._json_response(
                200,
                {
                    "ok": True,
                    "assetType": "video",
                    "isAuthentic": bool(verification_result["isAuthentic"]),
                    "status": str(verification_result["status"]),
                    "detail": str(verification_result["detail"]),
                    "sampledMoments": int(verification_result["sampledMoments"]),
                    "authenticMoments": int(verification_result["authenticMoments"]),
                    "tamperedMoments": int(verification_result["tamperedMoments"]),
                    "missingMoments": int(verification_result["missingMoments"]),
                },
            )
            return

        is_authentic = isinstance(verification_result, tuple) and bool(verification_result[0])

        if is_authentic:
            self._json_response(
                200,
                {
                    "ok": True,
                    "assetType": "image",
                    "isAuthentic": True,
                    "status": "Authentic",
                    "detail": (
                        "Embedded signature verified successfully and the visual fingerprint matched the signed reference."
                    ),
                },
            )
            return

        self._json_response(
            200,
            {
                "ok": True,
                "assetType": "image",
                "isAuthentic": False,
                "status": "AI/Tampered image",
                "detail": (
                    "No valid trusted proof was verified for this image. It is unsigned, altered, or not from the issuing authority."
                ),
            },
        )

    def _read_form_data(self) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
        content_length = int(self.headers.get("Content-Length", "0"))
        content_type = self.headers.get("Content-Type", "")
        body = self.rfile.read(content_length)
        return parse_multipart_form(content_type, body)

    def _serve_static(self, path: Path) -> None:
        if not path.exists():
            self._json_response(404, {"ok": False, "message": "Static file not found."})
            return

        self._serve_file(path)

    def _serve_file(self, path: Path, as_attachment: bool = False) -> None:
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if as_attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, status_code: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    ensure_runtime_dirs()
    server = ThreadingHTTPServer((HOST, PORT), DemoRequestHandler)
    print(f"Digital Trust Shield demo server running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
