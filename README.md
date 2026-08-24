# Digital Trust Shield

Digital Trust Shield is a hackathon prototype for verifying whether government posters, payment receipts, notices, PDFs, and shared screenshots are authentic or tampered.

The public repository intentionally contains product documentation, architecture, demo flow, and integration notes only. The private cryptographic signing and watermarking implementation is not published.

## Why This Exists

Important public and financial information is often shared through low-trust channels such as WhatsApp, screenshots, forwarded images, and PDFs. These files can be edited, recompressed, cropped, or forged, and ordinary users have no simple way to know whether a poster or receipt is genuine.

Digital Trust Shield solves this by attaching an invisible cryptographic proof to the visual document itself.

## Core Idea

1. A trusted authority signs a visual fingerprint of a poster, receipt, PDF page, or notice.
2. The proof is embedded invisibly into the image pixels using a resilient watermarking strategy.
3. A verifier app extracts the proof and validates it against the authority public key.
4. The user sees a simple result: authentic, fake/tampered, watermark not found, or verification failed.

## Current Product Scope

- Admin signing portal for authorities.
- FastAPI backend for signing, verification, metadata, audit logs, and chatbot services.
- Android verifier app for public users.
- Firebase Firestore for authorities, public keys, signed-document metadata, logs, and audit records.
- Local file storage fallback for signed outputs when Firebase Storage is unavailable.
- AI chatbot assistant using Tavily web search and Groq summarization.
- Voice input and multilingual chatbot support for English, Kannada, and Hindi.

## Architecture

```mermaid
flowchart LR
    Admin["Authority Admin"] --> Portal["Admin Web Portal"]
    Portal --> API["FastAPI Backend"]

    API --> KeyStore["Encrypted Local Private Key Store"]
    API --> Core["Private Signing and Verification Engine"]
    API --> Firestore["Firebase Firestore"]
    API --> LocalStorage["Local or Firebase File Storage"]

    User["Citizen / Verifier"] --> Android["Android Verification App"]
    Android --> API
    Android --> Speech["Android Speech Recognizer"]

    API --> Tavily["Tavily Web Search"]
    API --> Groq["Groq LLM Summary"]

    Firestore --> Android
```

## Signing Flow

```mermaid
sequenceDiagram
    participant Admin as Authority Admin
    participant Portal as Admin Portal
    participant API as FastAPI Backend
    participant Core as Private Signing Engine
    participant Store as Storage
    participant DB as Firestore

    Admin->>Portal: Upload poster, receipt, or PDF
    Portal->>API: POST /api/sign with authority and key id
    API->>API: Load encrypted private key locally
    API->>Core: Create visual fingerprint and sign it
    Core-->>API: Signed output with invisible proof
    API->>Store: Save signed output
    API->>DB: Save signed document metadata
    API-->>Portal: Return download URL and document id
```

## Verification Flow

```mermaid
sequenceDiagram
    participant User as User
    participant App as Android Verifier
    participant API as FastAPI Backend
    participant DB as Firestore
    participant Core as Private Verification Engine

    User->>App: Select received image or screenshot
    App->>API: POST /api/verify
    API->>DB: Fetch selected or active public keys
    API->>Core: Extract invisible proof
    API->>Core: Verify RSA signature and visual fingerprint
    Core-->>API: Authentic or not authentic
    API-->>App: Human-readable verification result
```

## AI Chatbot Flow

```mermaid
sequenceDiagram
    participant User as User
    participant App as Android Chatbot
    participant API as FastAPI Backend
    participant Tavily as Tavily Search
    participant Groq as Groq LLM

    User->>App: Ask by text or voice
    App->>API: POST /api/chat
    API->>Tavily: Search the web
    Tavily-->>API: Search results and snippets
    API->>Groq: Summarize with sources
    Groq-->>API: Final multilingual answer
    API-->>App: Answer and source list
```

## Security Model

- Private keys are never stored in Firebase.
- Private keys are encrypted and stored only on the backend machine.
- Android app receives only public keys and verification responses.
- Firestore stores authority metadata, public keys, signed-document metadata, verification logs, and audit logs.
- The public repository does not expose the private watermarking, signing, extraction, or screenshot-recovery implementation.

## Repository Publication Policy

This GitHub version is designed for public demonstration. It intentionally excludes:

- RSA private keys and key backups.
- Firebase service account credentials.
- Full signing and watermarking source code.
- Backend security-sensitive implementation files.
- Android and web app source code.
- Generated screenshots, payment images, QA artifacts, videos, and runtime logs.

See [docs/PUBLICATION_POLICY.md](docs/PUBLICATION_POLICY.md) for details.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, FastAPI |
| Signing core | RSA signatures, perceptual fingerprints, DCT watermarking |
| Admin portal | React, Vite, TypeScript |
| Mobile app | Android Kotlin, Jetpack Compose |
| Database | Firebase Firestore |
| Storage | Local storage fallback, Firebase Storage optional |
| AI assistant | Tavily Search API, Groq Chat Completions |
| Voice | Android Speech Recognizer |

## Demo Script

1. Admin creates an authority.
2. Admin generates a key pair.
3. Backend stores the private key encrypted locally.
4. Backend stores the public key in Firestore.
5. Admin uploads and signs a poster or receipt.
6. Signed output is shared through WhatsApp or downloaded to a phone.
7. User opens the Android verifier app.
8. User selects the received image or screenshot.
9. App calls the backend verification API.
10. App displays authentic or fake/tampered.
11. User opens the chatbot tab and asks questions by text or voice.

## Environment Variables

The private implementation uses environment variables similar to:

```env
FIREBASE_CREDENTIALS=secrets/serviceAccountKey.json
USE_LOCAL_STORAGE=true
LOCAL_UPLOAD_DIR=uploads
FIREBASE_STORAGE_BUCKET=
MASTER_KEY=your_fernet_master_key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
TAVILY_API_KEY=your_tavily_key
GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile
```

Do not commit real `.env` files or service account credentials.

## Public Repository Note

This repository is a public showcase version. The complete implementation is retained privately by the team for demo, evaluation, and further development.

## Team

Team HAHAHA

Project repository target:

```text
https://github.com/Hiteshacu/Digital_Trust_Shield-Team-HAHAHA...-.git
```
