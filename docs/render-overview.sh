#!/usr/bin/env bash
# Renders docs/overview.html to docs/images/overview.png at 2x.
set -euo pipefail
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
chromium --headless --disable-gpu --no-sandbox \
  --screenshot="$here/images/overview.png" \
  --window-size=1200,675 \
  --force-device-scale-factor=2 \
  --hide-scrollbars \
  "file://$here/overview.html" >/dev/null 2>&1
printf 'wrote %s\n' "$here/images/overview.png"
