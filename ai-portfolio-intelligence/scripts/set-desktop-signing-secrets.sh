#!/usr/bin/env bash
# Load desktop signing materials into GitHub Actions secrets.
# Run from anywhere after preparing the local files listed below.
#
# Required local files (you choose the paths):
#   1) Developer ID .p12   (macOS distribution, NOT "Apple Development")
#   2) Windows .pfx        (Authenticode / code-signing certificate)
#
# Optional:
#   3) App Store Connect .p8 API key (alternative to APPLE_ID + app password)
#
# Usage:
#   ./scripts/set-desktop-signing-secrets.sh \
#     --apple-p12 ~/certs/DeveloperID.p12 \
#     --apple-p12-password '...' \
#     --apple-identity 'Developer ID Application: Your Name (TEAMID)' \
#     --apple-id 'you@example.com' \
#     --apple-app-password 'xxxx-xxxx-xxxx-xxxx' \
#     --apple-team-id 'TEAMID' \
#     --windows-pfx ~/certs/windows-codesign.pfx \
#     --windows-pfx-password '...'

set -euo pipefail

APPLE_P12=""
APPLE_P12_PASSWORD=""
APPLE_IDENTITY=""
APPLE_ID=""
APPLE_APP_PASSWORD=""
APPLE_TEAM_ID=""
WINDOWS_PFX=""
WINDOWS_PFX_PASSWORD=""
KEYCHAIN_PASSWORD="portfolio-analyzer-ci"

usage() {
  sed -n '1,25p' "$0"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apple-p12) APPLE_P12="$2"; shift 2 ;;
    --apple-p12-password) APPLE_P12_PASSWORD="$2"; shift 2 ;;
    --apple-identity) APPLE_IDENTITY="$2"; shift 2 ;;
    --apple-id) APPLE_ID="$2"; shift 2 ;;
    --apple-app-password) APPLE_APP_PASSWORD="$2"; shift 2 ;;
    --apple-team-id) APPLE_TEAM_ID="$2"; shift 2 ;;
    --windows-pfx) WINDOWS_PFX="$2"; shift 2 ;;
    --windows-pfx-password) WINDOWS_PFX_PASSWORD="$2"; shift 2 ;;
    --keychain-password) KEYCHAIN_PASSWORD="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $1"; usage ;;
  esac
done

if ! command -v gh >/dev/null; then
  echo "Install GitHub CLI first: https://cli.github.com/"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Run: gh auth login"
  exit 1
fi

set_secret() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "Skipping empty secret: $name"
    return 0
  fi
  printf '%s' "$value" | gh secret set "$name"
  echo "Set $name"
}

if [[ -n "$APPLE_P12" ]]; then
  test -f "$APPLE_P12" || { echo "Missing Apple p12: $APPLE_P12"; exit 1; }
  APPLE_CERT_B64="$(base64 < "$APPLE_P12" | tr -d '\n')"
  set_secret APPLE_CERTIFICATE "$APPLE_CERT_B64"
  set_secret APPLE_CERTIFICATE_PASSWORD "$APPLE_P12_PASSWORD"
  set_secret APPLE_SIGNING_IDENTITY "$APPLE_IDENTITY"
  set_secret APPLE_ID "$APPLE_ID"
  set_secret APPLE_PASSWORD "$APPLE_APP_PASSWORD"
  set_secret APPLE_TEAM_ID "$APPLE_TEAM_ID"
  set_secret KEYCHAIN_PASSWORD "$KEYCHAIN_PASSWORD"
fi

if [[ -n "$WINDOWS_PFX" ]]; then
  test -f "$WINDOWS_PFX" || { echo "Missing Windows pfx: $WINDOWS_PFX"; exit 1; }
  WINDOWS_CERT_B64="$(base64 < "$WINDOWS_PFX" | tr -d '\n')"
  set_secret WINDOWS_CERTIFICATE "$WINDOWS_CERT_B64"
  set_secret WINDOWS_CERTIFICATE_PASSWORD "$WINDOWS_PFX_PASSWORD"
fi

echo
echo "Current repo secrets:"
gh secret list
echo
echo "Next:"
echo "  git tag desktop-v0.1.0"
echo "  git push origin desktop-v0.1.0"
