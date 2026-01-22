# Android Deep Links (TWA v2) Runbook

This repo ships an Android wrapper via Trusted Web Activity (TWA) so shared links can go:
share → install → open exact deep link → beat-this.

## What’s included

- Android App Links verification endpoint: `/.well-known/assetlinks.json` (served by API)
- Public event endpoint: `POST /api/events` for `app_open_deeplink`
- Android wrapper project: `apps/android-twa/` (opens the incoming URL fullscreen in TWA)

## 1) Configure Digital Asset Links (server)

Set these env vars on the web origin that serves `/s/*` (same origin as your shared links):

- `NEUROLEAGUE_ANDROID_ASSETLINKS_PACKAGE_NAME` (example: `com.neuroleague.twa`)
- `NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS` (comma-separated SHA256 fingerprints)
- Optional: `NEUROLEAGUE_ANDROID_INSTALL_URL` (Play Store URL used as an “Install App” CTA on share landings)

Verify:

- `curl -s https://YOUR_DOMAIN/.well-known/assetlinks.json | jq .`

If not configured, it returns `[]` (not verified).

## 2) Build and install the Android wrapper

Project: `apps/android-twa/`

Edit host + default URL:

- `apps/android-twa/app/src/main/res/values/strings.xml`
  - `host` (example: `neuroleague.example.com`)
  - `default_url` (example: `https://neuroleague.example.com/`)

Build a debug APK from Android Studio (or CI) and install on device/emulator.

Get SHA256 signing cert fingerprint:

- Debug keystore (typical):
  - `keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android | rg -n \"SHA256\"`

Set `NEUROLEAGUE_ANDROID_ASSETLINKS_SHA256_CERT_FINGERPRINTS` to match the fingerprint that signed the installed APK.

## 3) Verify App Links on device

Re-verify (Android 12+):

- `adb shell pm verify-app-links --re-verify com.neuroleague.twa`

Check current state:

- `adb shell pm get-app-links com.neuroleague.twa`

## 4) Deep link smoke test

Trigger an App Link intent:

- `adb shell am start -a android.intent.action.VIEW -d \"https://YOUR_DOMAIN/s/clip/r_seed_001?start=0.0&end=10.0&v=1&utm_source=test\"`

Expected:

- If verified, Android opens `com.neuroleague.twa` and displays the URL fullscreen.
- If not verified, it opens in the browser.

## 5) Verify `app_open_deeplink` analytics

The wrapper posts `app_open_deeplink` to `POST /api/events` when launched with an incoming URL.

Local test without Android:

- `curl -sS -X POST http://127.0.0.1:8000/api/events \\`
  `-H 'content-type: application/json' \\`
  `-d '{\"type\":\"app_open_deeplink\",\"url\":\"https://example.com/s/clip/r_seed_001?utm_source=test\",\"source\":\"manual\"}'`

To confirm ingestion locally, inspect `artifacts/neuroleague.db` and `events` table (or use existing Ops/analytics pages).

