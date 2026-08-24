# Architecture

Digital Trust Shield is organized around one security boundary: private signing operations happen only on the backend, while verification clients receive public keys and human-readable results.

## Components

```mermaid
flowchart TB
    subgraph ClientLayer["Client Layer"]
        AdminPortal["Admin Web Portal"]
        AndroidApp["Android Verification App"]
    end

    subgraph BackendLayer["Backend Layer"]
        FastAPI["FastAPI REST API"]
        SigningService["Signing Service"]
        VerificationService["Verification Service"]
        ChatService["Chatbot Service"]
        AuditService["Audit Service"]
    end

    subgraph PrivateCore["Private Core"]
        Fingerprint["Visual Fingerprint"]
        RSA["RSA Signature"]
        Watermark["Invisible Watermark"]
        Recovery["Screenshot and WhatsApp Recovery"]
    end

    subgraph DataLayer["Data Layer"]
        Firestore["Firebase Firestore"]
        Storage["Local or Firebase Storage"]
        KeyStore["Encrypted Local Private Keys"]
    end

    subgraph ExternalAI["External AI"]
        Tavily["Tavily Search"]
        Groq["Groq LLM"]
    end

    AdminPortal --> FastAPI
    AndroidApp --> FastAPI
    FastAPI --> SigningService
    FastAPI --> VerificationService
    FastAPI --> ChatService
    FastAPI --> AuditService
    SigningService --> PrivateCore
    VerificationService --> PrivateCore
    SigningService --> KeyStore
    SigningService --> Firestore
    VerificationService --> Firestore
    FastAPI --> Storage
    ChatService --> Tavily
    ChatService --> Groq
```

## Firestore Collections

| Collection | Purpose |
| --- | --- |
| `authorities` | Stores authority name, department, email, and status |
| `public_keys` | Stores public RSA keys and metadata |
| `signed_documents` | Stores signed document metadata and storage URL/path |
| `verification_logs` | Stores app verification results |
| `audit_logs` | Stores signing/key/audit events |

## Verification Result States

| Result | Meaning |
| --- | --- |
| `AUTHENTIC` | Hidden proof exists, signature is valid, and visual fingerprint matches |
| `WATERMARK_NOT_FOUND` | No Digital Trust Shield proof was found |
| `SIGNATURE_INVALID` | Proof exists but public key validation failed |
| `TAMPERED` | Proof exists but visual content changed |
| `ERROR` | Unexpected processing failure |

## Deployment Notes

- Backend should run on a trusted server or authority machine.
- Private keys must remain encrypted and local to the backend.
- Android app should call the backend over a reachable LAN or HTTPS URL.
- Firebase Storage is optional because local storage fallback is supported.
- Tavily and Groq API keys must stay in backend `.env`, never in the Android APK.
