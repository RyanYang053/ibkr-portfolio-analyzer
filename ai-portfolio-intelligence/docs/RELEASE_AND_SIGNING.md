# Release & Signing Runbook — shipping installable builds to other people

The desktop CI (`.github/workflows/desktop-release.yml`) already builds, **signs, notarizes,
verifies, launch-smoke-tests, and publishes a draft GitHub Release** for macOS (Apple Silicon +
Intel), Windows, and Linux. Nothing in the pipeline needs changing. The only things it can't do
for you are the parts that require **paid certificates and identity verification** — this runbook
walks through exactly those, then how to cut the release.

> Without certs, main-branch CI still builds **unsigned** installers (fine for your own testing —
> on macOS, right-click the app → Open to bypass Gatekeeper). But a signed/notarized release is
> what makes it "install like any normal app" for other people, with no scary warnings. Tagged
> `desktop-v*` releases **refuse to publish unsigned** — this is intentional.

---

## Part A — macOS (Developer ID + notarization)

**Cost:** Apple Developer Program, US$99/year.

1. **Enroll:** https://developer.apple.com/programs/ (needs your Apple ID; individual or company).
2. **Create a "Developer ID Application" certificate:** developer portal → Certificates, IDs &
   Profiles → Certificates → **+** → *Developer ID Application*. Follow the CSR steps, download the
   `.cer`, double-click to add it to **Keychain Access**.
3. **Export it as `.p12`:** in Keychain Access, find the cert (with its private key), right-click →
   Export → `.p12`, set an export password.
4. **Encode + collect the values** (run locally):
   ```bash
   base64 -i DeveloperID.p12 | pbcopy        # -> secret APPLE_CERTIFICATE (now on your clipboard)
   security find-identity -v -p codesigning  # -> the "Developer ID Application: NAME (TEAMID)" line
   ```
   - `APPLE_CERTIFICATE` = the base64 blob
   - `APPLE_CERTIFICATE_PASSWORD` = the export password from step 3
   - `APPLE_SIGNING_IDENTITY` = the full `Developer ID Application: NAME (TEAMID)` string
   - `APPLE_TEAM_ID` = the `TEAMID` in parentheses
5. **Notarization credentials — choose ONE method:**
   - **App-specific password (simplest):** https://appleid.apple.com → Sign-In & Security →
     App-Specific Passwords → generate one. Then `APPLE_ID` = your Apple ID email,
     `APPLE_PASSWORD` = that app-specific password.
   - **App Store Connect API key (better for CI):** App Store Connect → Users and Access →
     Integrations → Keys → generate. Then `APPLE_API_ISSUER` = issuer UUID, `APPLE_API_KEY` = key
     ID, `APPLE_API_KEY_PATH` = the downloaded `.p8` (the workflow reads it from this env).
6. `KEYCHAIN_PASSWORD` = any random string (optional; the workflow has a default).

---

## Part B — Windows (Authenticode)

**Cost:** ~US$200–400/year (OV) or more (EV).

⚠️ **Read this first — it's the real hurdle.** Since June 2023, CA/Browser-Forum rules require the
private key for standard **OV** certs to live on **FIPS hardware** (USB token / HSM). A key on a
hardware token **cannot** be exported to a `.pfx`, so the `WINDOWS_CERTIFICATE` (base64 `.pfx`)
path the workflow expects **won't work with a modern hardware-bound cert**. Your practical options:

- **Azure Trusted Signing** (recommended, cheap, cloud, CI-native) — ~US$10/month, no hardware.
  Requires switching the Windows signing step to the Azure signing action; tell me and I'll wire it in.
- **A cloud HSM signing service** (SSL.com eSigner, DigiCert KeyLocker) that exposes a `.pfx`-like
  credential or a signing API usable in CI.
- **EV cert on a token** — strongest trust (instant SmartScreen reputation) but token-bound, so
  not CI-exportable without a cloud KSP.
- **Ship unsigned on Windows** — users get a one-time SmartScreen "More info → Run anyway" prompt.
  Acceptable for a personal-use app shared with a few people; not for wide distribution.

If you get an exportable `.pfx` (legacy or via a cloud service):
```bash
base64 -i codesign.pfx        # -> secret WINDOWS_CERTIFICATE
```
- `WINDOWS_CERTIFICATE` = the base64 blob
- `WINDOWS_CERTIFICATE_PASSWORD` = the `.pfx` password

---

## Part C — Add the secrets to GitHub

Repo → **Settings → Secrets and variables → Actions → New repository secret**. Add each name/value
from Parts A and B. Minimum for a fully signed release:

| Platform | Required secrets |
|---|---|
| macOS | `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_TEAM_ID`, **and** either (`APPLE_ID` + `APPLE_PASSWORD`) or (`APPLE_API_ISSUER` + `APPLE_API_KEY` + `APPLE_API_KEY_PATH`) |
| Windows | `WINDOWS_CERTIFICATE`, `WINDOWS_CERTIFICATE_PASSWORD` (or switch to Azure Trusted Signing) |

---

## Part D — Cut the release

```bash
git checkout main && git pull
git tag desktop-v0.1.0
git push origin desktop-v0.1.0
```

The **Desktop** workflow then, per platform:
1. Runs the validate gates (API suite, golden master, point-in-time, no-trading boundary, smokes).
2. Builds the exact-SHA PyInstaller sidecar + static frontend.
3. Builds the installer (DMG / NSIS `.exe` / AppImage + DEB).
4. **Signs + notarizes**, then **verifies** (`codesign --verify`, `spctl --assess`,
   `stapler validate`; Windows `Get-AuthenticodeSignature` must be `Valid`).
5. Runs the **Tauri launch smoke** (actually boots the app).
6. **Publishes a draft GitHub Release** with all the installers attached.

## Part E — Publish

Repo → **Releases** → open the draft → add notes → **Publish**. Done — anyone can download the DMG
(Mac) or the NSIS installer (Windows) and install it like a normal app.

---

## Auto-update — wired; 3 steps to finish

The Tauri v2 updater is now fully wired: the Rust plugin is registered (`cargo check` passes),
the `updater:default` capability is granted, the frontend `UpdateChecker` checks on launch
(silent no-op until configured), and `tauri.conf.json` points `endpoints` at the repo's GitHub
Releases `latest.json`. Three things remain — all needing the **updater signing keypair, which
only you can hold**:

1. **Generate the keypair** (keep the private key secret):
   ```bash
   cd ai-portfolio-intelligence/apps/desktop
   npx tauri signer generate -w ~/.tauri/portfolio-analyzer.key
   # prints a PUBLIC key and writes the PRIVATE key to that path
   ```
2. **Set the public key + turn on update artifacts** in `apps/desktop/src-tauri/tauri.conf.json`:
   - replace `plugins.updater.pubkey` value `REPLACE_WITH_TAURI_UPDATER_PUBLIC_KEY` with the printed public key
   - add `"createUpdaterArtifacts": true` inside `bundle` (this makes the release build emit the
     signed `latest.json` + update bundles). *Only enable this once step 3 is done, or the release
     build will fail for lack of a signing key.*
3. **Add the private key as GitHub secrets:** `TAURI_SIGNING_PRIVATE_KEY` (the file's contents) and
   `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (blank if you didn't set one).

After that, every `desktop-v*` release ships an update manifest, and installed apps update
themselves on launch. Until then, the checker stays silent — so the app works normally today.

---

## Quick "just let me test it on my own Mac now" path (no certs)

```bash
cd ai-portfolio-intelligence
python3 scripts/build-macos-installer.py   # unsigned .app/.dmg (needs Rust + PyInstaller)
```
Then right-click the app → **Open** the first time to get past Gatekeeper.
