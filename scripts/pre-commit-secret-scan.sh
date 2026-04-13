#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DevCity Pulse — Pre-commit secret scanner
# Blocks commits that contain API keys, tokens, or other secrets.
#
# Install as a git hook:
#   cp scripts/pre-commit-secret-scan.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "🔍 Scanning staged files for secrets..."

BLOCKED=0

# ── 1. Block .env files from being staged ────────────────────────────────────
if git diff --cached --name-only | grep -qE '^\.env$|^\.env\.[^e]'; then
  echo -e "${RED}BLOCKED: .env file is staged for commit.${NC}"
  echo "  Add .env to .gitignore and run: git rm --cached .env"
  BLOCKED=1
fi

# ── 2. Scan for patterns that look like secrets ───────────────────────────────
SECRET_PATTERNS=(
  'WATSONX_API_KEY\s*=\s*[A-Za-z0-9_\-]{20,}'
  'IBMCLOUD_API_KEY\s*=\s*[A-Za-z0-9_\-]{20,}'
  'JWT_SECRET\s*=\s*[A-Za-z0-9_\-]{20,}'
  'REDDIT_CLIENT_SECRET\s*=\s*[A-Za-z0-9_\-]{10,}'
  'apikey\s*[=:]\s*["\x27][A-Za-z0-9_\-]{20,}'
  'Bearer [A-Za-z0-9_\-\.]{30,}'
)

for pattern in "${SECRET_PATTERNS[@]}"; do
  MATCHES=$(git diff --cached -U0 | grep '^\+' | grep -Ev '^\+\+\+' | grep -E "$pattern" || true)
  if [[ -n "$MATCHES" ]]; then
    echo -e "${RED}BLOCKED: Possible secret detected matching: $pattern${NC}"
    echo "$MATCHES" | head -5
    BLOCKED=1
  fi
done

# ── 3. Block known-insecure default values ────────────────────────────────────
INSECURE_DEFAULTS=(
  'change_me_in_production'
  'replace_with_long_random_secret'
  'your_key_here'
  'your_watsonx_api_key_here'
)

for val in "${INSECURE_DEFAULTS[@]}"; do
  MATCHES=$(git diff --cached -U0 | grep '^\+' | grep -Ev '^\+\+\+' | grep -F "$val" || true)
  if [[ -n "$MATCHES" ]]; then
    echo -e "${YELLOW}WARNING: Placeholder value '$val' found in staged changes.${NC}"
    echo "  Make sure this is only in .env.example (which is safe to commit)."
  fi
done

if [[ $BLOCKED -eq 1 ]]; then
  echo ""
  echo -e "${RED}Commit aborted. Remove secrets from staged files and try again.${NC}"
  exit 1
fi

echo "✓ No secrets detected in staged files."
exit 0
