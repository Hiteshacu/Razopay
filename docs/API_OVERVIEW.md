# API Overview

This document describes the public API shape at a high level. It does not include private implementation details.

## Health

```http
GET /api/health
```

Returns backend, Firestore, storage, and chatbot configuration status.

## Public Keys

```http
GET /api/keys/public
```

Returns active public keys for Android verification.

## Signing

```http
POST /api/sign
Content-Type: multipart/form-data
```

Fields:

- `file`
- `authority_id`
- `key_id`

High-level behavior:

1. Backend loads encrypted private key locally.
2. Backend creates and signs a visual fingerprint.
3. Backend embeds the signed proof invisibly.
4. Backend stores output and Firestore metadata.

## Verification

```http
POST /api/verify
Content-Type: multipart/form-data
```

Fields:

- `file`
- `key_id`

High-level behavior:

1. Backend extracts hidden proof if present.
2. Backend validates the proof against public keys.
3. Backend compares visual fingerprint to detect edits.
4. Backend returns a user-friendly result.

## Chatbot

```http
POST /api/chat
Content-Type: application/json
```

Request:

```json
{
  "message": "How can I verify a government poster?",
  "language": "en"
}
```

Supported language codes:

- `en` for English
- `kn` for Kannada
- `hi` for Hindi

High-level behavior:

1. Backend searches the web using Tavily.
2. Backend summarizes the result using Groq.
3. Backend returns answer and source list to the Android app.
