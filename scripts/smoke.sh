#!/usr/bin/env bash
# Post-deploy operational smoke test (Phase 6).
#
# Verifies the launch-critical contract against a RUNNING instance — not an
# in-process test double — so a deploy is provably serving before traffic is sent:
#   • liveness / readiness / health / version answer
#   • the public read surface is open WITHOUT auth (Public is truly public)
#   • a user-owned surface still requires auth (private data stays private)
#
# Usage:  scripts/smoke.sh [BASE_URL]      (default: http://localhost:8000)
# Exit:   0 = all checks pass; 1 = a check failed (details on stderr).
set -euo pipefail

BASE="${1:-${SMOKE_URL:-http://localhost:8000}}"
fail=0

# check <method> <path> <expected_status> <description>
check() {
  local method="$1" path="$2" want="$3" desc="$4"
  local got
  got="$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "${BASE}${path}" || echo 000)"
  if [ "$got" = "$want" ]; then
    printf '  ok   %-4s %-28s -> %s  (%s)\n' "$method" "$path" "$got" "$desc"
  else
    printf '  FAIL %-4s %-28s -> %s (want %s)  (%s)\n' "$method" "$path" "$got" "$want" "$desc" >&2
    fail=1
  fi
}

echo "smoke: ${BASE}"

# Liveness & readiness gates.
check GET /livez   200 "process is live"
check GET /readyz  200 "dependencies ready"
check GET /health  200 "health + info"
check GET /version 200 "api/schema version"

# Public read surface — open to anonymous visitors (no Authorization header).
check GET /companies 200 "public: reference corpus"
check GET /entities  200 "public: entity search"
check GET /dashboard 200 "public: aggregate discovery"

# Private surface — must reject an unauthenticated caller.
check GET /portfolios 401 "private: user portfolios locked"
check GET /watchlists 401 "private: watchlists locked"

if [ "$fail" -ne 0 ]; then
  echo "smoke: FAILED" >&2
  exit 1
fi
echo "smoke: PASSED"
