#!/usr/bin/env bash
# sync_nanobot_channels.sh — diff and optionally apply upstream nanobot changes
#
# Usage:
#   ./scripts/sync_nanobot_channels.sh [--apply] [--nanobot-dir DIR]
#
# Without --apply: shows a diff between the recorded upstream commit and HEAD.
# With    --apply: copies updated files, rewrites imports, and updates UPSTREAM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UPSTREAM_FILE="$REPO_ROOT/src/openharness/channels/UPSTREAM"
CHANNELS_DEST="$REPO_ROOT/src/openharness/channels"

# ---------- parse args ----------
APPLY=false
NANOBOT_DIR="${NANOBOT_DIR:-$HOME/nanobot}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true; shift ;;
    --nanobot-dir) NANOBOT_DIR="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# ---------- read recorded commit ----------
OLD_COMMIT=$(grep '^commit:' "$UPSTREAM_FILE" | awk '{print $2}')
echo "Upstream UPSTREAM commit : $OLD_COMMIT"

cd "$NANOBOT_DIR"
NEW_COMMIT=$(git rev-parse HEAD)
echo "Nanobot HEAD             : $NEW_COMMIT"

if [[ "$OLD_COMMIT" == "$NEW_COMMIT" ]]; then
  echo "Already up-to-date."
  exit 0
fi

# ---------- show diff ----------
echo ""
echo "=== diff nanobot/bus/ ==="
git diff "$OLD_COMMIT".."$NEW_COMMIT" -- nanobot/bus/ || true

echo ""
echo "=== diff nanobot/channels/ ==="
git diff "$OLD_COMMIT".."$NEW_COMMIT" -- nanobot/channels/ || true

if [[ "$APPLY" == false ]]; then
  echo ""
  echo "Run with --apply to apply these changes."
  exit 0
fi

# ---------- apply ----------
echo ""
echo "Applying changes..."

# Copy files
cp nanobot/bus/events.py  "$CHANNELS_DEST/bus/events.py"
cp nanobot/bus/queue.py   "$CHANNELS_DEST/bus/queue.py"
for f in nanobot/channels/*.py; do
  fname="$(basename "$f")"
  [[ "$fname" == "__init__.py" ]] && continue
  cp "$f" "$CHANNELS_DEST/impl/$fname"
done

# Rewrite imports
for f in "$CHANNELS_DEST/bus/"*.py "$CHANNELS_DEST/impl/"*.py; do
  sed -i \
    -e 's/from nanobot\.bus\./from openharness.channels.bus./g' \
    -e 's/from nanobot\.channels\./from openharness.channels.impl./g' \
    -e 's/from nanobot\.config\.schema import/from openharness.config.schema import/g' \
    -e 's/from nanobot\.utils\.helpers import/from openharness.utils.helpers import/g' \
    -e 's/from nanobot\.config\.loader import/from openharness.config.loader import/g' \
    "$f"
  # Replace loguru
  sed -i \
    's/^from loguru import logger$/import logging\nlogger = logging.getLogger(__name__)/' \
    "$f"
done

# Update UPSTREAM
SYNC_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
sed -i "s/^commit: .*/commit: $NEW_COMMIT/" "$UPSTREAM_FILE"
sed -i "s/^synced: .*/synced: $SYNC_TIME/" "$UPSTREAM_FILE"

echo "Done. Updated UPSTREAM to $NEW_COMMIT (synced $SYNC_TIME)"
