#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Fetch the PostgreSQL dump from Google Drive so `make demo` / `make restore`
# work on ANY machine (the ~783 MB dump is git-ignored and DVC-tracked, but the
# DVC remote is local-only — this script provides a zero-setup public download).
#
# Idempotent: if database/lol_draft.dump already exists with the right md5, it
# does nothing. Otherwise it downloads from the public Drive link and verifies
# the md5 before putting the file in place (a partial/corrupt download is never
# left at the final path).
#
# No gdown/Python needed: the drive.usercontent.google.com endpoint with
# `confirm=t` bypasses Google's large-file virus-scan interstitial, so a plain
# curl (or wget) streams the bytes directly.
#
# Override the source with DUMP_URL=... ./scripts/fetch_dump.sh if you mirror the
# dump elsewhere (e.g. S3 / GitHub Release).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DUMP_PATH="${PROJECT_DIR}/database/lol_draft.dump"
EXPECTED_MD5="367c127c874f502ba0a129bfcc1d95fd"   # matches database/lol_draft.dump.dvc
FILE_ID="1zhWlsXZsbZthnlGvNnUvghNHWjXqaKeu"
DUMP_URL="${DUMP_URL:-https://drive.usercontent.google.com/download?id=${FILE_ID}&export=download&confirm=t}"

# md5 helper that works on both macOS (`md5 -q`) and Linux (`md5sum`).
md5_of() {
    if command -v md5 >/dev/null 2>&1; then
        md5 -q "$1"
    else
        md5sum "$1" | awk '{print $1}'
    fi
}

# Already present and intact? Nothing to do.
if [ -f "$DUMP_PATH" ]; then
    if [ "$(md5_of "$DUMP_PATH")" = "$EXPECTED_MD5" ]; then
        echo "✅ Dump already present and verified: $DUMP_PATH"
        exit 0
    fi
    echo "⚠️  Existing dump has an unexpected md5 — re-downloading."
fi

mkdir -p "${PROJECT_DIR}/database"
TMP="${DUMP_PATH}.part"
trap 'rm -f "$TMP"' EXIT

echo "⬇️  Downloading DB dump (~783 MB) from Google Drive ..."
if command -v curl >/dev/null 2>&1; then
    curl -L --fail --progress-bar -o "$TMP" "$DUMP_URL"
elif command -v wget >/dev/null 2>&1; then
    wget --no-verbose -O "$TMP" "$DUMP_URL"
else
    echo "❌ Neither curl nor wget is available. Install one, or download the dump"
    echo "   manually to: $DUMP_PATH"
    echo "   Source: https://drive.google.com/file/d/${FILE_ID}/view"
    exit 1
fi

echo "🔎 Verifying integrity ..."
GOT_MD5="$(md5_of "$TMP")"
if [ "$GOT_MD5" != "$EXPECTED_MD5" ]; then
    echo "❌ Checksum mismatch — download is corrupt or the file changed."
    echo "   expected: $EXPECTED_MD5"
    echo "   got:      $GOT_MD5"
    echo "   (If you intentionally updated the dump, refresh EXPECTED_MD5 here"
    echo "    and in database/lol_draft.dump.dvc.)"
    exit 1
fi

mv "$TMP" "$DUMP_PATH"
trap - EXIT
echo "✅ Dump downloaded and verified: $DUMP_PATH"
