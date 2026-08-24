# Digital Trust Shield Admin Portal

React + Vite admin console for the FastAPI signing backend.

## Features

- Simple hackathon admin login.
- Create issuing authorities.
- Generate RSA key pairs through the backend.
- Show public key IDs and SHA-256 fingerprints.
- Sign images/PDFs using the existing Python watermark engine.
- Show Firebase Storage URL and signed document ID.
- List signed documents and hash-chained audit logs.

## Setup

```powershell
cd admin-portal
copy .env.example .env
npm install
npm run dev
```

The portal expects the backend at `VITE_API_BASE_URL=http://127.0.0.1:8000`.

## Demo Login

Default backend `.env`:

- Username: `admin`
- Password: `admin123`

Use stronger values for public demos.

