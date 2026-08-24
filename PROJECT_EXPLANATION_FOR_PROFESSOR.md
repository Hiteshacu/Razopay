# Digital Trust Shield - Professor Explanation Guide

## 1. Simple One-Line Explanation

Digital Trust Shield verifies whether a shared poster, payment receipt, notice, PDF, or screenshot is genuine by embedding an invisible cryptographic proof inside the visual content itself.

## 2. Problem Being Solved

Many official documents and payment proofs are shared through low-trust channels such as WhatsApp, screenshots, downloaded images, and PDFs. These files can be edited, recompressed, cropped, or forged. Normal users usually cannot tell whether the image is original or modified.

This project solves that by combining:

- Cryptographic signatures, to prove the document came from a trusted authority.
- Perceptual image fingerprinting, to detect visual changes.
- Invisible DCT watermarking, to store the proof inside the pixels.
- Backend-controlled private keys, so only trusted authorities can sign.
- Public-key verification, so citizens can check authenticity safely.

## 3. Main Idea In Easy Words

Think of each official poster as having a hidden seal.

1. The authority creates a visual fingerprint of the poster.
2. The backend signs that fingerprint using a private RSA key.
3. The signed proof is hidden inside the image pixels using watermarking.
4. A user later uploads the received image to the verifier.
5. The verifier extracts the hidden proof.
6. It checks whether the signature matches the public key.
7. It also checks whether the current visual content still matches the signed fingerprint.

If both checks pass, the document is authentic. If the proof is missing, invalid, or the content changed, the document is rejected.

## 4. Project Layers

The project has three main product layers and one reusable cryptographic core.

| Layer | Folder or Files | Purpose |
| --- | --- | --- |
| Cryptographic core | `utils.py`, `sign_poster.py`, `verify_poster.py`, `watermark_embedder.py`, `watermark_extractor.py`, `pdf_support.py`, `video_support.py` | Performs RSA signing, fingerprinting, DCT watermark embedding/extraction, PDF support, video support, and screenshot recovery |
| FastAPI backend | `backend/app/` | Product API for authorities, keys, signing, verification, audit logs, Firebase, and chatbot |
| Admin portal | `admin-portal/src/` | React web console for officials to create authorities, generate keys, and sign documents |
| Android verifier | `android-verifier/app/src/main/` | Kotlin/Jetpack Compose public app that uploads media for verification and uses chatbot support |
| Local demo server | `app.py`, `demo.html`, `demo.js` | Simple browser demo for generating keys, signing media, and verifying media locally |

## 5. Important Source Files

### Root Cryptographic Core

`utils.py`

- Defines global constants.
- Reads and writes images.
- Generates perceptual fingerprints.
- Signs and verifies RSA-PSS signatures.
- Builds and parses watermark payloads.
- Creates deterministic DCT block order.
- Maintains audit logs.
- Maintains `official_registry.json` for recovery of forwarded or screenshot media.
- Contains local Windows DPAPI-based private-key hardening for the prototype key files.

`watermark_embedder.py`

- Embeds the signed proof into the luminance channel of the image.
- Splits the image into 8x8 DCT blocks.
- Stores bits by changing the ordering of selected DCT coefficients.
- Repeats each payload bit across many blocks for robustness.

`watermark_extractor.py`

- Reads the hidden watermark back from DCT blocks.
- Uses majority voting to recover bits.
- Supports resize recovery factors for images that were scaled.
- Can measure watermark correlation against an expected payload.

`sign_poster.py`

- Main signing entry point for images.
- Also redirects PDFs to `pdf_support.py` and videos to `video_support.py`.
- Creates fingerprint, signs it, embeds it, registers it, and self-checks the signed result.

`verify_poster.py`

- Main verification entry point.
- Verifies normal images directly.
- Supports forwarded-image recovery.
- Supports screenshot crop and resize recovery.
- Uses registry-based recovery only with cryptographic and watermark evidence.

`pdf_support.py`

- Converts every PDF page into an image.
- Signs each page independently.
- Rebuilds the PDF from signed page images.
- Verifies PDFs page by page.

`video_support.py`

- Samples moments across a video timeline.
- Embeds proof into selected frames.
- Preserves audio when possible.
- Verifies enough sampled frames to decide whether the video is authentic.

### Backend

`backend/app/main.py`

- Creates the FastAPI application.
- Enables CORS for the admin portal.
- Serves local uploaded signed files from `/uploads`.
- Registers all API routes.
- Provides `/api/health`.

`backend/app/config.py`

- Loads backend `.env`.
- Defines Firebase credentials path, storage mode, upload directories, admin login, CORS, Tavily/Groq keys, and storage settings.

`backend/app/schemas.py`

- Defines the request and response models for authorities, keys, signing, verification, login, and chatbot.

`backend/app/services/key_service.py`

- Creates authorities.
- Generates RSA 2048-bit key pairs.
- Stores public keys in Firestore.
- Sends private keys to encrypted local storage only.

`backend/app/services/private_key_store.py`

- Encrypts private keys with Fernet using `MASTER_KEY`.
- Stores encrypted keys under `backend/secure_private_keys/{authority_id}/{key_id}.enc`.
- Temporarily decrypts a private key only for signing, then deletes the temp PEM file.

`backend/app/services/signing_service.py`

- Accepts uploaded PNG/JPG/JPEG/PDF files.
- Validates selected authority and key.
- Saves original file.
- Calls the cryptographic core through `trust_shield_adapter.py`.
- Saves signed output locally or to Firebase Storage.
- Stores signed-document metadata in Firestore.
- Records audit events.

`backend/app/services/verification_service.py`

- Accepts uploaded verification images.
- Loads the selected public key.
- Calls the cryptographic verifier.
- If the selected key fails, retries other active keys.
- Returns user-friendly states such as `AUTHENTIC`, `TAMPERED`, `WATERMARK_NOT_FOUND`, or `SIGNATURE_INVALID`.
- Logs verification events.

`backend/app/services/firebase_service.py`

- Wraps Firestore reads and writes.
- Uploads signed files to Firebase Storage when local storage is disabled.

`backend/app/services/audit_service.py`

- Stores audit logs with hash chaining.
- Each audit record stores the previous hash and current hash.
- This helps detect tampering in the audit history.

`backend/app/services/chat_service.py`

- Uses Tavily for web search.
- Uses Groq chat completions for summarization.
- Supports English, Kannada, and Hindi.

### Admin Portal

`admin-portal/src/App.tsx`

- Main React app.
- Loads authorities, public keys, signed documents, and audit logs.
- Switches between dashboard, authorities, keys, signing, documents, and audit pages.

`admin-portal/src/api/client.ts`

- Configures Axios.
- Default backend URL is `http://127.0.0.1:8000`.
- Defines frontend TypeScript types matching backend responses.

`admin-portal/src/pages/Authorities.tsx`

- Lets an admin create an authority.

`admin-portal/src/pages/KeyManagement.tsx`

- Lets an admin generate a key pair for an authority.
- Shows public key fingerprints.

`admin-portal/src/pages/SignDocument.tsx`

- Lets an admin upload a poster or PDF.
- Sends file, authority ID, and key ID to `/api/sign`.
- Displays the signed output URL.

### Android Verifier

`android-verifier/app/src/main/java/com/digitaltrustshield/verifier/api/VerificationApi.kt`

- Defines Retrofit endpoints:
  - `GET api/keys/public`
  - `POST api/verify`
  - `POST api/chat`

`android-verifier/app/src/main/java/com/digitaltrustshield/verifier/api/ApiClient.kt`

- Configures Retrofit, OkHttp timeouts, JSON parsing, and API base URL.

`android-verifier/app/src/main/java/com/digitaltrustshield/verifier/MainActivity.kt`

- Contains two tabs:
  - Verification
  - Chatbot
- Loads public keys.
- Lets user choose an image.
- Uploads it to the backend for verification.
- Displays the result and authority information.
- Supports voice input for chatbot using Android speech recognition.

## 6. Cryptographic Algorithm Step By Step

### 6.1 Image Fingerprint

The project does not sign raw image bytes. Raw bytes change when an image is recompressed, saved again, or shared through WhatsApp.

Instead, it creates a 128-bit visual fingerprint:

- 64 bits from dHash, which captures relative brightness differences.
- 64 bits from pHash-like DCT features, which capture low-frequency visual structure.

This fingerprint is small, stable, and based on visual content.

Before creating the fingerprint, the image is canonicalized:

- The image is converted into DCT blocks.
- The DCT coefficients reserved for watermarking are neutralized.
- This prevents the watermark itself from changing the fingerprint.

### 6.2 RSA Signature

The fingerprint is hashed with SHA-256. The backend signs that digest with RSA-PSS-SHA256.

Important details:

- RSA key size is 2048 bits.
- Signature size is 256 bytes.
- Private key signs only on the backend.
- Public key verifies on the backend and is safe to publish.

### 6.3 Watermark Payload

The payload hidden inside the image has this logical format:

```text
DTS2 magic marker
4-byte checksum
payload version
fingerprint length
signature length
16-byte reference fingerprint
256-byte RSA signature
```

The magic marker tells the extractor this is a Digital Trust Shield watermark. The checksum detects corrupted extracted payloads.

### 6.4 DCT Watermark Embedding

The image is divided into 8x8 blocks. This is the same block size used in JPEG-style frequency processing.

For each block:

1. Convert image to YCrCb.
2. Use the Y channel, which stores luminance/brightness.
3. Apply DCT to each 8x8 block.
4. Pick mid-frequency coefficient pairs.
5. For bit `1`, force coefficient A to be stronger than coefficient B.
6. For bit `0`, force coefficient B to be stronger than coefficient A.
7. Convert back using inverse DCT.

The project uses coefficient pairs such as:

```text
(3,2) vs (2,3)
(2,1) vs (1,2)
```

These are mid-frequency coefficients. They are better than very low frequencies because they are less visually obvious, and better than very high frequencies because they survive compression more reliably.

### 6.5 Bit Repetition And Majority Vote

One bit is not stored only once. The same payload bit is repeated across several DCT blocks.

During extraction:

- Every repeated copy votes for `0` or `1`.
- The majority vote becomes the recovered bit.

This makes the watermark more resistant to noise, recompression, blur, and screenshots.

### 6.6 Deterministic Block Order

The project does not embed bits sequentially from top-left to bottom-right. It uses a deterministic shuffled order.

The modern permutation is built with SHA-256 and a fixed seed. This makes the block order reproducible outside Python and harder to locate by simply inspecting blocks in order.

## 7. Signing Flow

### Product Flow Through FastAPI

1. Admin logs into the React portal.
2. Admin creates an authority.
3. Backend stores that authority in Firestore.
4. Admin generates a key pair.
5. Backend creates RSA private and public keys.
6. Backend encrypts the private key locally using Fernet.
7. Backend stores only the public key and metadata in Firestore.
8. Admin uploads a poster or PDF.
9. Backend checks authority ID and key ID.
10. Backend writes the uploaded file to local or temporary storage.
11. Backend temporarily decrypts the private key.
12. Backend calls `sign_file_adapter`.
13. Adapter calls `sign_poster`.
14. `sign_poster` routes to image, PDF, or video signing.
15. For image signing, the core creates a fingerprint, signs it, embeds the watermark, registers the output, and self-checks.
16. Backend stores the signed file locally or in Firebase Storage.
17. Backend writes signed-document metadata to Firestore.
18. Backend records an audit event.
19. Admin receives a signed file URL.

### Image Signing Internals

1. Read image.
2. Generate reference fingerprint.
3. Hash fingerprint with SHA-256.
4. Load private key.
5. Sign digest with RSA-PSS.
6. Build watermark payload.
7. Embed payload in DCT blocks.
8. Save signed output.
9. Register signed asset in `official_registry.json`.
10. Verify the signed output immediately.
11. Simulate forwarded/WhatsApp-style copies and verify those too.

The self-check is important because it prevents the system from producing a signed file that cannot later be verified.

## 8. Verification Flow

### Android To Backend Flow

1. Android app calls `GET /api/keys/public`.
2. User selects an active authority/public key.
3. User selects an image from gallery.
4. Android uploads the image and key ID to `POST /api/verify`.
5. Backend writes the upload to a temp file.
6. Backend loads public key PEM from Firestore.
7. Backend calls `verify_file_adapter`.
8. Adapter calls `verify_poster`.
9. Verifier extracts the watermark and reference fingerprint.
10. Verifier validates RSA signature against the selected public key.
11. Verifier generates current image fingerprint.
12. Verifier compares current fingerprint against signed reference fingerprint.
13. Backend returns a human-readable result.
14. Backend writes a verification log.

### Verification Result Meanings

| Result | Meaning |
| --- | --- |
| `AUTHENTIC` | Watermark exists, RSA signature is valid, and visual fingerprint matches |
| `WATERMARK_NOT_FOUND` | No hidden Digital Trust Shield proof was found |
| `SIGNATURE_INVALID` | Hidden proof exists but does not verify with the public key |
| `TAMPERED` | Proof exists but current visual content differs from signed content |
| `ERROR` | Unexpected processing or setup failure |

## 9. Screenshot And Forwarded-Image Recovery

Shared screenshots are difficult because the image may be:

- Compressed.
- Resized.
- Displayed inside a phone UI.
- Cropped with borders.
- Blurred by capture or sharing.

The verifier therefore tries several recovery strategies:

1. Direct modern watermark verification.
2. Full-frame registry recovery for images resized by messaging apps.
3. Screenshot candidate generation by trimming borders.
4. Foreground and edge-based crop candidates.
5. Resize restoration to known signed geometry.
6. Watermark correlation against the expected registered payload.
7. Legacy watermark extraction as a fallback.

The registry is not used alone as proof. A registry match must still pass public-key signature validation, visual fingerprint matching, and watermark evidence checks.

## 10. PDF Flow

PDFs are handled page by page.

Signing:

1. Render each PDF page to an image using PyMuPDF.
2. Sign each rendered page independently.
3. Embed the watermark in every page image.
4. Register each page with its page number.
5. Rebuild the PDF from signed page images.

Verification:

1. Render the submitted PDF page by page.
2. Extract watermark from each page image.
3. Verify signature and fingerprint per page.
4. Return a list of page results.

This lets the system say exactly which page is authentic or fake.

## 11. Video Flow

Videos are handled by sampling frames across the timeline.

Signing:

1. Read FPS, frame count, size, and duration.
2. Choose sample frame indices across the video.
3. Sign and watermark selected frames.
4. Rebuild the visual track.
5. Preserve audio with FFmpeg when possible.
6. Register every signed frame as a video-frame asset.

Verification:

1. Choose the same kind of sample positions.
2. Verify each sampled frame.
3. Count authentic, tampered, and missing moments.
4. Decide whether enough of the timeline contains trusted proof.

The verifier requires a ratio of authentic samples and rejects if any sampled moment is tampered.

## 12. Backend API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Backend/Firebase/storage/chatbot status |
| `/api/auth/login` | POST | Demo admin login |
| `/api/authorities` | POST | Create authority |
| `/api/authorities` | GET | List authorities |
| `/api/keys/generate` | POST | Generate RSA key pair for an authority |
| `/api/keys/public` | GET | List public keys |
| `/api/sign` | POST multipart | Sign uploaded poster/PDF |
| `/api/verify` | POST multipart | Verify uploaded image |
| `/api/chat` | POST JSON | Ask Tavily/Groq chatbot |
| `/api/documents` | GET | List signed document metadata |
| `/api/audit` | GET | List audit logs |

## 13. Firestore Collections

| Collection | Purpose |
| --- | --- |
| `authorities` | Authority name, department, email, status |
| `public_keys` | Public RSA keys and metadata |
| `signed_documents` | Signed file metadata and download/storage path |
| `verification_logs` | Public verification attempts and results |
| `audit_logs` | Signing, key-generation, and authority events |

## 14. Storage Model

The backend supports two storage modes.

Local mode:

- Original files go under `backend/uploads/original_documents/`.
- Signed files go under `backend/uploads/signed_documents/`.
- Temp verification uploads go under `backend/uploads/temp/`.
- Signed files are served through `/uploads/...`.

Firebase Storage mode:

- Signed files are uploaded to Firebase Storage.
- Backend stores the Firebase path and URL in Firestore.

## 15. Security Model

The most important security boundary is:

Private keys stay on the backend. Public clients never receive private keys.

In the newer backend:

- Private keys are encrypted with Fernet.
- The encryption key comes from `MASTER_KEY`.
- The encrypted private keys are stored locally.
- Firestore receives only public keys and metadata.
- Temporary decrypted private key files are deleted after signing.

In the older prototype:

- Root `private_key.pem` can be sealed with Windows DPAPI.
- Audit and backup folders are permission-hardened.

Important warning: this local workspace contains private-key-related files and backend secret files. Do not publish them. The `.gitignore` and docs clearly say these must remain private.

## 16. Admin Portal Explanation

The admin portal is for trusted authorities.

It does not perform signing in the browser. That is intentional. Browser-side signing would expose sensitive logic and possibly private keys.

Admin portal responsibilities:

1. Login.
2. Create issuing authorities.
3. Generate public/private key pair through the backend.
4. Upload documents for signing.
5. View signed document records.
6. View audit logs.

## 17. Android App Explanation

The Android app is for citizens or verifiers.

It does not need a private key. It only needs:

- Backend URL.
- Public keys.
- User-selected image.

Main screens:

1. Verification tab.
2. Chatbot tab.

The current Android picker selects images using `image/*`. The backend has broader core support for PDFs and videos, but this Android UI is currently image-focused.

## 18. Chatbot Feature

The chatbot is called DTS Sahayak.

It supports:

- English.
- Kannada.
- Hindi.
- Text input.
- Voice input.
- Web search through Tavily.
- Summarization through Groq.

It is useful for public-safety questions, government scheme questions, cyber-safety help, and poster verification guidance.

## 19. Local Demo Server

`app.py` is a simpler HTTP server for a local demo.

It provides:

- `/demo` for the demo page.
- `/api/status` to check key readiness.
- `/api/generate-keys` to generate root RSA keys.
- `/api/sign` to sign uploaded image/video.
- `/api/verify` to verify uploaded image/video.
- `/api/download/{filename}` to download signed output.

This is separate from the production-like FastAPI backend.

## 20. How To Demo To Professor

Use this order:

1. Start with the problem:
   - Fake payment screenshots and edited public notices spread easily.
   - Metadata and QR codes can be removed or copied.

2. Explain the solution:
   - We hide a signed cryptographic proof inside the visual document itself.

3. Show authority setup:
   - Create authority in admin portal.
   - Generate RSA key pair.
   - Explain private key remains encrypted on backend.
   - Explain public key is safe to share.

4. Show signing:
   - Upload poster or receipt.
   - Backend creates fingerprint.
   - Backend signs fingerprint.
   - Backend embeds proof invisibly.
   - Signed document is stored and listed.

5. Show verification:
   - Open Android app.
   - Select signed image.
   - Select authority key.
   - Tap Verify.
   - Show `AUTHENTIC`.

6. Show tamper case:
   - Modify amount/date/text in the image.
   - Upload again.
   - Show `TAMPERED` or verification failure.

7. Explain why it is robust:
   - Uses perceptual fingerprinting, not raw bytes.
   - Uses DCT watermarking, not metadata.
   - Uses RSA signatures, not simple hidden text.

## 21. Advanced Professor Talking Points

### Why not just hash the file?

A normal file hash changes if WhatsApp recompresses the image. This project uses a perceptual fingerprint that tolerates small compression changes while still detecting meaningful visual edits.

### Why not just add metadata?

Metadata is often stripped when images are shared or screenshotted. This project embeds proof directly into the pixels using DCT coefficients.

### Why RSA?

RSA uses a private/public key model. The authority signs with the private key. Anyone with the public key can verify. This prevents attackers from creating valid signatures.

### Why DCT?

DCT works in the frequency domain. JPEG compression also uses DCT-like ideas, so carefully chosen mid-frequency coefficients can survive common sharing transformations better than simple pixel-level hiding.

### Why use both signature and fingerprint?

The signature proves the authority signed a specific fingerprint. The fingerprint proves the visible content still looks like the signed original.

### Why does the backend own signing?

If signing happened in the Android app or browser, the private key could be extracted. Keeping signing on the backend protects the issuing authority.

### Why use audit hash chaining?

Each audit log contains the hash of the previous log. If someone edits an old audit event, the chain breaks.

## 22. Current Limitations And Honest Notes

- Local workspace contains sensitive implementation and key files. They should not be pushed publicly.
- Backend `.env`, Firebase service account JSON, encrypted private keys, and root private keys must remain private.
- Android currently allows cleartext HTTP and has a hardcoded backend IP for LAN demo. Production should use HTTPS and environment-based configuration.
- Admin login returns a static demo token. Production needs real authentication and authorization.
- Android verification UI currently selects images only, although backend/core supports more media types.
- CodeQL workflow appears to use `verification_app` as Android working directory, but this project folder is named `android-verifier`.
- Firebase security rules must be configured carefully before production.
- DCT watermarking is robust to moderate transformations, not unlimited attacks such as extreme cropping, heavy blur, aggressive recompression, or full visual recreation.

## 23. Final Short Explanation To Memorize

Digital Trust Shield is a document authenticity system. When an authority signs a poster or receipt, the backend creates a perceptual fingerprint of the visual content, signs it using RSA-PSS, and embeds that signed proof invisibly inside the image using DCT watermarking. Later, the verifier extracts the hidden proof, checks the RSA signature using the authority public key, and compares the current visual fingerprint with the signed reference. If the signature and fingerprint both match, the document is authentic. If the watermark is missing, the signature is invalid, or the visual content changed, the system reports it as fake or tampered.

