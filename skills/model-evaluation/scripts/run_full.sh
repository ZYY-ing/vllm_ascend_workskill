#!/usr/bin/env bash
# Hallusion inference only: preflight -> bounded requests -> integrity report.
set -euo pipefail
umask 077

KIT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HALL="${HALLUSION_HOME:-}"
API="${HALLUSION_API:-}"
MODEL="${HALLUSION_MODEL:-}"
CONTAINER="${HALLUSION_CONTAINER:-}"
PYTHON="${PYTHON:-python3}"
DATA="${HALLUSION_DATA:-}"
ROOT="${HALLUSION_ROOT:-}"
OUTPUT="${HALLUSION_OUTPUT:-}"
LIMIT="${HALLUSION_LIMIT:-0}"
CONCURRENCY="${HALLUSION_CONCURRENCY:-1}"
MAX_TOKENS="${HALLUSION_MAX_TOKENS:-4096}"
TEMPERATURE="${HALLUSION_TEMPERATURE:-0.6}"
TOP_K="${HALLUSION_TOP_K:-}"
TOP_P="${HALLUSION_TOP_P:-}"
REPETITION_PENALTY="${HALLUSION_REPETITION_PENALTY:-}"
SKIP_SPECIAL_TOKENS="${HALLUSION_SKIP_SPECIAL_TOKENS:-}"
REASONING_EFFORT="${HALLUSION_REASONING_EFFORT:-}"
REQUEST_TIMEOUT="${HALLUSION_REQUEST_TIMEOUT:-1200}"
CHECK_ONLY=false

usage() {
  cat <<'EOF'
Usage: bash run_full.sh --home PROJECT --api URL --model ID [options]
  --home PATH                    Runtime project; never use the installed skill directory
  --data PATH / --root PATH      Defaults: PROJECT/HallusionBench/{HallusionBench.json,}
  --api URL / --model ID         Existing OpenAI-compatible API ending in /v1; no model start
  --container NAME               Optional docker exec; script/data paths must be visible identically
  --python PATH                  Python in selected runtime (default: python3)
  --limit N                      0=all; positive N=official first N (default: 0)
  --concurrency N                Maximum in-flight inference requests (default: 1)
  --max_tokens N                 Output budget (default: 4096)
  --temperature F                Explicit sampling (default: 0.6, same as direct client)
  --top_k N / --top_p F / --repetition_penalty F
  --reasoning_effort MODE        high|max|no_think; check the deployed model template
  --skip_special_tokens / --no_skip_special_tokens
  --request_timeout SECONDS      Socket-operation timeout, not whole-request deadline
  --output PATH                  Must be a new directory; default PROJECT/outputs/<timestamp>-<PID>
  --check-only                   Only dataset/image/health/model preflight
  -h, --help                     Show help without dependencies or API access
CLI > HALLUSION_* environment > defaults. Hyphen/underscore option spellings are aliases.
Inference does not resume automatically and does not run the paid judge API.
EOF
}
while [ "$#" -gt 0 ]; do
  option="${1//_/-}"
  case "$option" in
    -h|--help) usage; exit 0 ;;
    --check-only) CHECK_ONLY=true; shift; continue ;;
    --skip-special-tokens) SKIP_SPECIAL_TOKENS=true; shift; continue ;;
    --no-skip-special-tokens) SKIP_SPECIAL_TOKENS=false; shift; continue ;;
    --home) variable=HALL ;;
    --api) variable=API ;;
    --model) variable=MODEL ;;
    --container) variable=CONTAINER ;;
    --python) variable=PYTHON ;;
    --data) variable=DATA ;;
    --root) variable=ROOT ;;
    --output) variable=OUTPUT ;;
    --limit) variable=LIMIT ;;
    --concurrency) variable=CONCURRENCY ;;
    --max-tokens) variable=MAX_TOKENS ;;
    --temperature) variable=TEMPERATURE ;;
    --top-k) variable=TOP_K ;;
    --top-p) variable=TOP_P ;;
    --repetition-penalty) variable=REPETITION_PENALTY ;;
    --reasoning-effort) variable=REASONING_EFFORT ;;
    --request-timeout) variable=REQUEST_TIMEOUT ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  if [ "$#" -lt 2 ] || [[ "$2" == --* ]]; then
    echo "Missing value for $1" >&2; exit 2
  fi
  printf -v "$variable" '%s' "$2"
  shift 2
done
: "${HALL:?Pass --home or set HALLUSION_HOME}"
: "${API:?Pass --api or set HALLUSION_API}"
: "${MODEL:?Pass --model or set HALLUSION_MODEL}"
[[ "$LIMIT" =~ ^[0-9]+$ && "$CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || {
  echo 'limit must be nonnegative; concurrency must be positive' >&2; exit 2;
}
DATA="${DATA:-$HALL/HallusionBench/HallusionBench.json}"
ROOT="${ROOT:-$HALL/HallusionBench}"
options=(--home "$HALL" --api "$API" --model "$MODEL" --data "$DATA" --root "$ROOT"
  --python "$PYTHON" --limit "$LIMIT" --concurrency "$CONCURRENCY"
  --max-tokens "$MAX_TOKENS" --temperature "$TEMPERATURE" --request-timeout "$REQUEST_TIMEOUT")
extra=()
for spec in 'TOP_K:top-k' 'TOP_P:top-p' 'REPETITION_PENALTY:repetition-penalty' 'REASONING_EFFORT:reasoning-effort'; do
  variable="${spec%%:*}"
  if [ -n "${!variable}" ]; then extra+=("--${spec#*:}" "${!variable}"); fi
done
case "$SKIP_SPECIAL_TOKENS" in
  true) extra+=(--skip-special-tokens) ;;
  false) extra+=(--no-skip-special-tokens) ;;
  '') ;;
  *) echo 'skip_special_tokens must be true or false' >&2; exit 2 ;;
esac
if [ -n "$OUTPUT" ]; then options+=(--output "$OUTPUT"); fi
if "$CHECK_ONLY"; then options+=(--check-only); fi
if [ -n "$CONTAINER" ] && [ ! -f /.dockerenv ]; then
  # Pass the optional model API key by environment name, never as a value in argv.
  docker_options=()
  if [ -n "${HY4_API_KEY:-}" ]; then docker_options+=(-e HY4_API_KEY); fi
  exec docker exec -i "${docker_options[@]}" "$CONTAINER" bash "$KIT/$(basename -- "${BASH_SOURCE[0]}")" "${options[@]}" "${extra[@]}"
fi
"$PYTHON" - "$API" <<'PY'
import sys
from urllib.parse import urlsplit
u = urlsplit(sys.argv[1])
if u.scheme not in ('http', 'https') or not u.netloc or u.username or u.password or u.query or u.fragment:
    raise SystemExit('Use an API base URL without embedded credentials, query or fragment; pass authentication privately')
PY
STAMP="$(date +%Y%m%d_%H%M%S)-$$"
RUN="${OUTPUT:-$HALL/outputs/hallusionbench-$STAMP}"
if [ -e "$RUN" ]; then echo 'Output already exists; select a new directory' >&2; exit 2; fi
mkdir -p "$HALL/logs"
"$PYTHON" "$KIT/preflight.py" --data "$DATA" --root "$ROOT" --api "$API" --model "$MODEL" --limit "$LIMIT" \
  2>&1 | tee "$HALL/logs/preflight-$STAMP.log"
if "$CHECK_ONLY"; then exit 0; fi
echo "RUN=$RUN"
"$PYTHON" -u "$KIT/run_hallusionbench_hy4.py" --data "$DATA" --root "$ROOT" --api "$API" --model "$MODEL" \
  --limit "$LIMIT" --concurrency "$CONCURRENCY" --max-tokens "$MAX_TOKENS" --temperature "$TEMPERATURE" \
  --request-timeout "$REQUEST_TIMEOUT" --output "$RUN" "${extra[@]}" \
  2>&1 | tee "$HALL/logs/hallusionbench-$STAMP.log"
"$PYTHON" "$KIT/check_results.py" --data "$DATA" --run "$RUN"
