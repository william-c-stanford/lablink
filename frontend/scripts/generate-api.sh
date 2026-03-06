#!/usr/bin/env bash
# generate-api.sh — Fetch the live OpenAPI spec from the backend and regenerate
# the TypeScript client types.
#
# Usage:
#   ./scripts/generate-api.sh               # Use running backend (localhost:8000)
#   ./scripts/generate-api.sh --local-file  # Use bundled openapi.json (offline)
#   LABLINK_API_URL=https://api.lablink.io ./scripts/generate-api.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
OPENAPI_FILE="$FRONTEND_DIR/openapi.json"

API_URL="${LABLINK_API_URL:-http://localhost:8000}"
USE_LOCAL_FILE=false

for arg in "$@"; do
  case $arg in
    --local-file) USE_LOCAL_FILE=true ;;
    --api-url=*) API_URL="${arg#*=}" ;;
  esac
done

echo "🔧 LabLink API Client Generator"
echo "──────────────────────────────────"

if [ "$USE_LOCAL_FILE" = false ]; then
  echo "🌐 Fetching OpenAPI spec from $API_URL ..."
  if curl -sf "$API_URL/openapi.json" -o "$OPENAPI_FILE.tmp" 2>/dev/null; then
    mv "$OPENAPI_FILE.tmp" "$OPENAPI_FILE"
    echo "✅ Spec downloaded to openapi.json"
  elif curl -sf "$API_URL/api/openapi.json" -o "$OPENAPI_FILE.tmp" 2>/dev/null; then
    mv "$OPENAPI_FILE.tmp" "$OPENAPI_FILE"
    echo "✅ Spec downloaded from /api/openapi.json"
  else
    echo "⚠️  Backend not reachable — using bundled openapi.json"
  fi
fi

echo ""
echo "📦 Generating TypeScript types..."
cd "$FRONTEND_DIR"

npx openapi-typescript openapi.json -o src/api/schema.d.ts

echo ""
node scripts/build-client.mjs

echo "🎉 Done! Your typed API client is ready."
