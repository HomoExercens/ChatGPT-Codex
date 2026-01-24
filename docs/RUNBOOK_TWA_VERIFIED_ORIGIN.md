# TWA Verified Origin Runbook (Digital Asset Links)

Trusted Web Activity (TWA) “app feel” depends on Android verifying that your Android package owns the web origin.
That verification uses **Digital Asset Links** (DAL) served from:

`https://<YOUR_DOMAIN>/.well-known/assetlinks.json`

This doc focuses on the *verified origin* part (domain + DAL), not general Android project setup.

## 0) What you need (non-negotiable)

- A **stable HTTPS origin** (real domain or stable subdomain)
  - Works in a normal browser on a real device
  - Serves:
    - `/play` (home)
    - `/s/*` (share landings)
    - `/.well-known/assetlinks.json`
- Your Android package name
- SHA-256 fingerprint(s) of the cert(s) that sign your APK/AAB

If the origin changes (ex: random `*.trycloudflare.com`), verification breaks and links open in the browser.

## 1) Pick a stable origin

Recommended options:

- Production: `neuroleague.example.com`
- Staging/preview: `preview.neuroleague.example.com`

Not suitable for verified origin:

- `localhost`
- random preview URLs like `https://<random>.trycloudflare.com`

## 2) Serve `/.well-known/assetlinks.json`

NeuroLeague serves `/.well-known/assetlinks.json` via the API router using env vars:

- `NEUROLEAGUE_ANDROID_ASSETLINKS_PACKAGE_NAME` (example: `com.neuroleague.twa`)
- `NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS`
  - Comma-separated list of fingerprints
  - Format: `AA:BB:CC:...` (32 bytes / 64 hex, colon-separated)

If not configured, the endpoint returns `[]` (meaning “not verified”).

### 2-A) Reference payload template

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.neuroleague.twa",
      "sha256_cert_fingerprints": ["AA:BB:CC:...:ZZ"]
    }
  }
]
```

## 3) Get SHA-256 fingerprints

Debug keystore (common):

`keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android | rg -n "SHA256"`

Release keystore:

- Use your release keystore + alias, then extract the SHA-256 fingerprint.
- Put both debug + release fingerprints in `NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS` if you want both builds to verify.

## 4) Verify on-device

Re-verify (Android 12+):

- `adb shell pm verify-app-links --re-verify com.neuroleague.twa`

Inspect status:

- `adb shell pm get-app-links com.neuroleague.twa`

Deep-link smoke test:

- `adb shell am start -a android.intent.action.VIEW -d "https://YOUR_DOMAIN/s/clip/r_seed_001?start=0.0&end=10.0&v=1&utm_source=android_alpha"`

Expected:

- Verified: opens in the TWA app fullscreen.
- Not verified: opens in the browser.

## 5) Preview/staging notes

If you want “stable preview” without a VPS:

- Use a **stable domain** (you control) and a stable routing method (ex: Cloudflare **named tunnel**).
- A quick tunnel random URL is fine for playtests, but not for DAL verification.

Do not commit fingerprints or secrets to git; treat keystores and signing material as private.

