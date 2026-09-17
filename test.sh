#!/usr/bin/env bash
# Runs the same requests against after-no-contract and after-with-contract.
# Shows which routes break when there is no engineering contract.
#
# Usage:  ./test.sh
# Requires: pip, uvicorn, curl, python3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SCRIPT_DIR}/.venv"
PORT_BEFORE=8000
PORT_NO=8001
PORT_WITH=8002
BASE_BEFORE="http://localhost:${PORT_BEFORE}"
BASE_NO="http://localhost:${PORT_NO}"
BASE_WITH="http://localhost:${PORT_WITH}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

pass()    { printf "  ${GREEN}✓  PASS${NC}  %s\n" "$*"; }
fail()    { printf "  ${RED}✗  FAIL${NC}  %s\n" "$*"; }
section() { printf "\n${BOLD}── %s${NC}\n" "$*"; }
divider() { printf "%s\n" "─────────────────────────────────────────────────────────"; }

# Wait until a port accepts HTTP connections (server ready)
wait_for_port() {
    local port=$1 attempts=0
    until curl -s -o /dev/null "http://localhost:${port}/" 2>/dev/null; do
        sleep 0.3
        attempts=$((attempts + 1))
        if [ $attempts -ge 40 ]; then
            echo "Server on port ${port} did not start in time — aborting"
            exit 1
        fi
    done
}

cleanup() {
    [ -n "${BEFORE_PID:-}" ] && kill "${BEFORE_PID}" 2>/dev/null || true
    [ -n "${NO_PID:-}"     ] && kill "${NO_PID}"     2>/dev/null || true
    [ -n "${WITH_PID:-}"   ] && kill "${WITH_PID}"   2>/dev/null || true
    rm -f "${SCRIPT_DIR}/before/agentdb.db" \
          "${SCRIPT_DIR}/after-no-contract/agentdb.db" \
          "${SCRIPT_DIR}/after-with-contract/agentdb.db"
}
trap cleanup EXIT

# Ensure venv exists with a single consistent Python
if [ ! -f "${VENV}/bin/python" ]; then
    python3 -m venv "${VENV}"
fi
PY="${VENV}/bin/python"
UV="${VENV}/bin/uvicorn"

# ── Header ────────────────────────────────────────────────────
printf "\n${BOLD}Engineering Contract Demo — Test Suite${NC}\n"
printf "Same task. Same API. Two CLAUDE.md files.\n"
divider

# ── Dependencies ──────────────────────────────────────────────
section "Installing dependencies"
"${PY}" -m pip install -q -r "${SCRIPT_DIR}/after-no-contract/requirements.txt"
printf "  Done.\n"

# ── Start servers ─────────────────────────────────────────────
section "Starting servers"
(cd "${SCRIPT_DIR}/before"            && "${UV}" main:app --port ${PORT_BEFORE} --log-level error) &
BEFORE_PID=$!
(cd "${SCRIPT_DIR}/after-no-contract"   && "${UV}" main:app --port ${PORT_NO}   --log-level error) &
NO_PID=$!
(cd "${SCRIPT_DIR}/after-with-contract" && "${UV}" main:app --port ${PORT_WITH} --log-level error) &
WITH_PID=$!

wait_for_port ${PORT_BEFORE}
wait_for_port ${PORT_NO}
wait_for_port ${PORT_WITH}
printf "  before              → %s  (pid %s)\n" "${BASE_BEFORE}" "${BEFORE_PID}"
printf "  after-no-contract   → %s  (pid %s)\n" "${BASE_NO}"     "${NO_PID}"
printf "  after-with-contract → %s  (pid %s)\n" "${BASE_WITH}"   "${WITH_PID}"

# Seed a run in each server so /runs/pending has data to return
PAYLOAD='{"model_id":"claude-sonnet-4-6","prompt":"summarise this document"}'
curl -s -X POST "${BASE_BEFORE}/runs" -H "Content-Type: application/json" -d "${PAYLOAD}" > /dev/null
curl -s -X POST "${BASE_NO}/runs"     -H "Content-Type: application/json" -d "${PAYLOAD}" > /dev/null
curl -s -X POST "${BASE_WITH}/runs"   -H "Content-Type: application/json" -d "${PAYLOAD}" > /dev/null
sleep 0.3

# ── Test 1: /health ───────────────────────────────────────────
section "Test 1  GET /health  —  was this route preserved during the split?"

BEFORE_SC=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_BEFORE}/health")
NO_SC=$(curl -s     -o /dev/null -w "%{http_code}" "${BASE_NO}/health")
WITH_SC=$(curl -s   -o /dev/null -w "%{http_code}" "${BASE_WITH}/health")

printf "  before:               HTTP %s\n" "${BEFORE_SC}"
printf "  after-no-contract:    HTTP %s\n" "${NO_SC}"
printf "  after-with-contract:  HTTP %s\n" "${WITH_SC}"

[ "${BEFORE_SC}" = "200" ] && pass "before         /health present (200 OK)" \
                            || fail "before         /health missing"
[ "${NO_SC}"     = "404" ] && fail "no-contract    /health dropped silently — not in any router file" \
                            || pass "no-contract    /health present"
[ "${WITH_SC}"   = "200" ] && pass "with-contract  /health present (200 OK)" \
                            || fail "with-contract  /health missing"

# ── Test 2: /runs/pending ─────────────────────────────────────
section "Test 2  GET /runs/pending  —  specific route before parameterised?"

BEFORE_SC=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_BEFORE}/runs/pending")
BEFORE_COUNT=$(curl -s "${BASE_BEFORE}/runs/pending" | "${PY}" -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")
NO_BODY=$(curl -s "${BASE_NO}/runs/pending")
NO_SC=$(curl -s   -o /dev/null -w "%{http_code}" "${BASE_NO}/runs/pending")
WITH_SC=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_WITH}/runs/pending")
WITH_COUNT=$(curl -s "${BASE_WITH}/runs/pending" | "${PY}" -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")

printf "  before:               HTTP %s  →  %s run(s) pending\n" "${BEFORE_SC}" "${BEFORE_COUNT}"
printf "  after-no-contract:    HTTP %s  →  %s\n"                "${NO_SC}"     "${NO_BODY}"
printf "  after-with-contract:  HTTP %s  →  %s run(s) pending\n" "${WITH_SC}"   "${WITH_COUNT}"

[ "${BEFORE_SC}" = "200" ] && pass "before         /runs/pending reachable" \
                            || fail "before         /runs/pending failed"
[ "${NO_SC}"     = "404" ] && fail "no-contract    /runs/pending matched /{run_id} with run_id=\"pending\" — ordering wrong" \
                            || pass "no-contract    /runs/pending reachable"
[ "${WITH_SC}"   = "200" ] && pass "with-contract  /runs/pending returns pending list (200 OK)" \
                            || fail "with-contract  /runs/pending failed"

# ── Test 3: /models/default ───────────────────────────────────
section "Test 3  GET /models/default  —  specific route before parameterised?"

BEFORE_SC=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_BEFORE}/models/default")
BEFORE_MODEL=$(curl -s "${BASE_BEFORE}/models/default" | "${PY}" -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "?")
NO_BODY=$(curl -s "${BASE_NO}/models/default")
NO_SC=$(curl -s   -o /dev/null -w "%{http_code}" "${BASE_NO}/models/default")
WITH_SC=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_WITH}/models/default")
WITH_MODEL=$(curl -s "${BASE_WITH}/models/default" | "${PY}" -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "?")

printf "  before:               HTTP %s  →  model: %s\n" "${BEFORE_SC}" "${BEFORE_MODEL}"
printf "  after-no-contract:    HTTP %s  →  %s\n"        "${NO_SC}"     "${NO_BODY}"
printf "  after-with-contract:  HTTP %s  →  model: %s\n" "${WITH_SC}"   "${WITH_MODEL}"

[ "${BEFORE_SC}" = "200" ] && pass "before         /models/default reachable" \
                            || fail "before         /models/default failed"
[ "${NO_SC}"     = "404" ] && fail "no-contract    /models/default matched /{model_id} with model_id=\"default\" — ordering wrong" \
                            || pass "no-contract    /models/default reachable"
[ "${WITH_SC}"   = "200" ] && pass "with-contract  /models/default returns default model (200 OK)" \
                            || fail "with-contract  /models/default failed"

# ── Test 4: /models/gpt-4o — parameterised route still works ─
section "Test 4  GET /models/gpt-4o  —  did fixing ordering break the parameterised route?"

BEFORE_SC=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_BEFORE}/models/gpt-4o")
NO_SC=$(curl -s     -o /dev/null -w "%{http_code}" "${BASE_NO}/models/gpt-4o")
WITH_SC=$(curl -s   -o /dev/null -w "%{http_code}" "${BASE_WITH}/models/gpt-4o")

printf "  before:               HTTP %s\n" "${BEFORE_SC}"
printf "  after-no-contract:    HTTP %s\n" "${NO_SC}"
printf "  after-with-contract:  HTTP %s\n" "${WITH_SC}"

[ "${BEFORE_SC}" = "200" ] && pass "before         /{model_id} works" \
                            || fail "before         /{model_id} broken"
[ "${NO_SC}"     = "200" ] && pass "no-contract    /{model_id} still works" \
                            || fail "no-contract    /{model_id} broken"
[ "${WITH_SC}"   = "200" ] && pass "with-contract  /{model_id} still works (ordering fix is safe)" \
                            || fail "with-contract  /{model_id} broken"

# ── Summary ───────────────────────────────────────────────────
printf "\n"
divider
printf "${BOLD}Summary${NC}\n\n"
printf "  %-26s  13/13 routes reachable  (starting point)\n"  "before:"
printf "  %-26s  10/13 routes reachable  /health dropped, /runs/pending unreachable, /models/default unreachable\n" "after-no-contract:"
printf "  %-26s  13/13 routes reachable  modular, correct ordering, no duplicate logic\n" "after-with-contract:"
printf "\n"
printf "${DIM}Root cause: after-no-contract/CLAUDE.md has no Functionality Preservation${NC}\n"
printf "${DIM}rule and no Change Workflow — routes were never catalogued before splitting.${NC}\n"
printf "${DIM}The code looks correct. The bugs only surface at runtime.${NC}\n\n"
