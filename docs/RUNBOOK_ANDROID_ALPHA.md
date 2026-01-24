# Android Alpha Runbook (TWA)

Goal: ship an Android-first “app feel” wrapper using Trusted Web Activity (TWA) for a web origin that serves NeuroLeague.

This repo already includes a deeper technical guide: `docs/RUNBOOK_ANDROID_DEEPLINKS.md`. This doc is the “alpha checklist” version.

## 0) Non-negotiables

- You need a **stable HTTPS origin** (a real domain or a stable subdomain) that serves:
  - `/play` (default entry)
  - `/s/*` share landings
  - `/.well-known/assetlinks.json`
- Localhost and random-preview URLs (ex: `*.trycloudflare.com`) are not suitable for App Links verification:
  - verification is domain-scoped and expects a stable origin,
  - users will get browser opens instead of “installed app opens the link”.

## 1) Pick the alpha origin

Choose one:

- **Real domain** (best): `neuroleague.example.com`
- **Stable preview domain** (acceptable for alpha): `preview.yourdomain.com`

Make sure the origin is reachable from a real Android device over HTTPS.

## 2) Digital Asset Links (verification)

Android App Links require `https://<origin>/.well-known/assetlinks.json` to match:

- the Android package name, and
- the SHA-256 fingerprint(s) of the signing certificate(s) that sign the APK/AAB.

### 2-A) How this repo serves `assetlinks.json`

NeuroLeague serves `/.well-known/assetlinks.json` from the API based on env vars:

- `NEUROLEAGUE_ANDROID_ASSETLINKS_PACKAGE_NAME` (example: `com.neuroleague.twa`)
- `NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS` (comma-separated, example includes debug + release)

If not configured, it returns an empty list `[]` (not verified).

### 2-B) Template (reference)

If you ever need to host it statically, the payload should look like:

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.neuroleague.twa",
      "sha256_cert_fingerprints": [
        "AA:BB:CC:...:ZZ"
      ]
    }
  }
]
```

### 2-C) Get your SHA-256 signing fingerprint

Debug keystore (typical):

`keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android | rg -n "SHA256"`

Use that fingerprint (or your release keystore fingerprint) in `NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS`.

## 3) Configure the TWA wrapper project

Project: `apps/android-twa/`

Update these strings:

- `apps/android-twa/app/src/main/res/values/strings.xml#L4`
  - `host` (your stable domain)
  - `default_url` (must point to `/play`, keep it as the app’s “home”)

## 4) Build + install (debug)

From `apps/android-twa/`:

- `./gradlew assembleDebug`
- Install the APK on a device/emulator (Android Studio or `adb install`).

## 5) Verify App Links on device

Re-verify (Android 12+):

- `adb shell pm verify-app-links --re-verify com.neuroleague.twa`

Check current state:

- `adb shell pm get-app-links com.neuroleague.twa`

Deep link smoke test:

- `adb shell am start -a android.intent.action.VIEW -d "https://YOUR_DOMAIN/s/clip/r_seed_001?start=0.0&end=10.0&v=1&utm_source=android_alpha"`

Expected:

- Verified: opens in the TWA app fullscreen.
- Not verified: opens in the browser.

## 6) Alpha limitations (what “won’t work” yet)

- Quick Tunnel random URLs are not stable enough for reliable App Links verification.
- Without a stable origin + `assetlinks.json`, Android will not “install → open exact share link” reliably.

