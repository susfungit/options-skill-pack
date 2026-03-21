#!/bin/bash
# Run once after cloning: bash setup.sh
# Generates .claude/settings.json with the correct absolute path for this machine.

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
MARKETPLACE_PATH="$PROJECT_ROOT/.claude/local-marketplace"
SETTINGS_FILE="$PROJECT_ROOT/.claude/settings.json"

cat > "$SETTINGS_FILE" <<EOF
{
  "enabledPlugins": {
    "bull-put-spread-selector@options-skill-pack": true
  },
  "extraKnownMarketplaces": {
    "options-skill-pack": {
      "source": {
        "source": "directory",
        "path": "$MARKETPLACE_PATH"
      }
    }
  }
}
EOF

echo "✓ Written: $SETTINGS_FILE"
echo "  Marketplace path: $MARKETPLACE_PATH"
