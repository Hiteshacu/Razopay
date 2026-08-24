# Digital Trust Shield Backend

FastAPI backend for signing and verifying official posters, PDFs, bills, receipts, and notices with the existing RSA + DCT watermarking core.

## Security Model

- Private keys are never stored in Firebase.
- `POST /api/keys/generate` creates a key pair on the backend.
- The private key is encrypted locally with Fernet using `MASTER_KEY`.
- The encrypted private key is stored under `backend/secure_private_keys/{authority_id}/{key_id}.enc`.
- The public key is saved in Firestore under `public_keys`.
- Signing decrypts the private key only into a short-lived temp PEM file, then deletes it.

Production upgrade: replace local Fernet storage with Google Cloud Secret Manager, Cloud KMS, HSM, or a signing-only service account.

## Setup

1. Create a Firebase project.
2. Enable Firestore and create the default database.
3. Firebase Storage is optional. You can keep `USE_LOCAL_STORAGE=true` if Blaze billing is not available.
4. Download a Firebase Admin SDK service account JSON.
5. Place it at `backend/secrets/serviceAccountKey.json`.
6. Create `.env` from `.env.example`.
7. Generate a Fernet key:

```powershell
python generate_master_key.py
```

8. Paste the output into `MASTER_KEY`.
9. For no-billing mode, keep:

```text
USE_LOCAL_STORAGE=true
LOCAL_UPLOAD_DIR=uploads
FIREBASE_STORAGE_BUCKET=
STORAGE_MAKE_PUBLIC=false
```

10. If you later enable Firebase Storage, set `USE_LOCAL_STORAGE=false` and fill `FIREBASE_STORAGE_BUCKET`.
11. Install dependencies:

```powershell
pip install -r requirements.txt
```

12. Start the API:

```powershell
run_server.cmd
```

The API runs at `http://127.0.0.1:8000`.

Signed files in local mode are served from `http://127.0.0.1:8000/uploads/...`.

## Main Endpoints

- `POST /api/auth/login`
- `POST /api/authorities`
- `GET /api/authorities`
- `POST /api/keys/generate`
- `GET /api/keys/public`
- `POST /api/sign`
- `POST /api/verify`
- `GET /api/documents`
- `GET /api/audit`

## Firebase Collections

- `authorities`
- `public_keys`
- `signed_documents`
- `verification_logs`
- `audit_logs`

## Firebase Storage Paths

- `signed_documents/{authority_id}/{document_id}/signed_output.png`
- `signed_documents/{authority_id}/{document_id}/signed_output.pdf`
- `public_keys/{authority_id}/{key_id}.pem` optional

## Local Storage Paths

- `backend/uploads/original_documents/`
- `backend/uploads/signed_documents/`
- `backend/uploads/temp/`

## Suggested Firebase Rules

```js
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /public_keys/{keyId} {
      allow read: if true;
      allow write: if false;
    }
    match /signed_documents/{docId} {
      allow read: if true;
      allow write: if false;
    }
    match /verification_logs/{logId} {
      allow create: if true;
      allow read, update, delete: if false;
    }
    match /authorities/{authorityId} {
      allow read: if true;
      allow write: if false;
    }
    match /audit_logs/{logId} {
      allow read, write: if false;
    }
  }
}
```

```js
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /signed_documents/{allPaths=**} {
      allow read: if true;
      allow write: if false;
    }
    match /verification_uploads/{allPaths=**} {
      allow read, write: if false;
    }
    match /public_keys/{allPaths=**} {
      allow read: if true;
      allow write: if false;
    }
  }
}
```
