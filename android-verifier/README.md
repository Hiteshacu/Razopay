# Digital Trust Shield Verifier Android App

Kotlin + Jetpack Compose verifier app for the hackathon demo.

## Verification Flow

1. App loads public keys from `GET /api/keys/public`.
2. User selects an image from gallery.
3. User selects authority/public key.
4. App uploads the image and key ID to `POST /api/verify`.
5. FastAPI runs the Python watermark verification engine.
6. App displays `Authentic`, `Fake / Tampered`, `Watermark Not Found`, or `Signature Invalid`.

## Setup

1. Open `android-verifier/` in Android Studio.
2. Start the backend on your laptop:

```powershell
cd backend
run_server.cmd
```

3. For Android emulator, the default API URL is:

```kotlin
http://10.0.2.2:8000/
```

4. For a physical phone, update `API_BASE_URL` in `app/build.gradle.kts` to your laptop LAN IP:

```kotlin
buildConfigField("String", "API_BASE_URL", "\"http://192.168.1.10:8000/\"")
```

5. Build and run the app.

## Demo

- Pick a signed image downloaded from the admin portal.
- Select the issuing authority key.
- Tap Verify.
- Edit or screenshot an unsigned/tampered version and verify again.

