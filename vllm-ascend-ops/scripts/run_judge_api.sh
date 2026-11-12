#!/usr/bin/env bash
set -euo pipefail
umask 077

finish() {
  local rc=$?
  trap - EXIT
  unset HALLUSION_JUDGE_API_KEY
  if [ "$rc" -eq 0 ]; then
    printf '\nJudge completed. Exit code: %s\n' "$rc"
  else
    printf '\nJudge failed/interrupted. Exit code: %s; inspect the log and keep existing caches.\n' "$rc" >&2
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

KIT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HALL="${HALLUSION_HOME:?Set HALLUSION_HOME to the HallusionBench project directory}"
D="$HALL/HallusionBench"
RUN="${1:-${HALLUSION_RUN:-}}"
if [ -z "$RUN" ]; then
  read -rp 'Completed inference RUN directory: ' RUN || exit 2
fi
: "${RUN:?An existing completed inference directory is required}"
EVAL="${HALLUSION_EVAL_DIR:-$RUN/evaluation}"
PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$KIT:$KIT/judge-deps${PYTHONPATH:+:$PYTHONPATH}"
 : "${HALLUSION_JUDGE_BASE_URL:?Set the OpenAI-compatible API base URL}"
export HALLUSION_JUDGE_BASE_URL
: "${HALLUSION_JUDGE_MODEL:?Set the exact judge model or endpoint ID}"
export HALLUSION_JUDGE_MODEL
export HALLUSION_JUDGE_CONCURRENCY="${HALLUSION_JUDGE_CONCURRENCY:-1}"
[[ "$HALLUSION_JUDGE_CONCURRENCY" =~ ^[0-9]+$ ]] && \
  (( HALLUSION_JUDGE_CONCURRENCY >= 1 && HALLUSION_JUDGE_CONCURRENCY <= 64 )) || \
  { echo 'Judge concurrency must be an integer between 1 and 64'; exit 2; }
echo "Judge concurrency: $HALLUSION_JUDGE_CONCURRENCY"

"$PYTHON" "$KIT/check_results.py" --data "$D/HallusionBench.json" --run "$RUN"
"$PYTHON" -c 'import openai,numpy,prettytable,tqdm; assert hasattr(openai,"OpenAI")'
mkdir -p "$EVAL"
exec 9> "$EVAL/.judge.lock"
flock -n 9 || { echo 'This evaluation is already running'; exit 1; }
if [ -f "$EVAL/.judge_completed" ]; then
  "$PYTHON" - "$D" "$RUN" "$EVAL" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
d,run,evaluation=map(Path,sys.argv[1:])
previous=json.loads((evaluation/'judge_config.json').read_text())
expected=dict(model=os.environ['HALLUSION_JUDGE_MODEL'],
              base_url=os.environ['HALLUSION_JUDGE_BASE_URL'],
              result_sha256=hashlib.sha256((run/'HallusionBench_result.json').read_bytes()).hexdigest(),
              official_utils_sha256=hashlib.sha256((d/'utils.py').read_text(encoding='utf-8').encode()).hexdigest())
for field,value in expected.items():
    if previous.get(field)!=value:
        raise RuntimeError(f'Completed evaluation differs in {field}; select a new HALLUSION_EVAL_DIR')
PY
  echo "Already completed: $EVAL"
  exit 0
fi

if [ -z "${HALLUSION_JUDGE_API_KEY:-}" ]; then
  read -rsp 'Judge API Key (hidden): ' HALLUSION_JUDGE_API_KEY || exit 2
  echo
fi
: "${HALLUSION_JUDGE_API_KEY:?API Key must not be empty}"
export HALLUSION_JUDGE_API_KEY

cp "$D/evaluation.py" "$D/utils.py" "$EVAL/"
cp "$RUN/HallusionBench_result.json" "$EVAL/"
"$PYTHON" - "$D" "$EVAL" <<'PY'
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from prepare_concurrent_judge import adapt_concurrent_utils, adapt_evaluation

d, evaluation = map(Path, sys.argv[1:])
source = (d/'utils.py').read_text(encoding='utf-8')
config = dict(model=os.environ['HALLUSION_JUDGE_MODEL'],
              base_url=os.environ['HALLUSION_JUDGE_BASE_URL'],
              sdk_version=importlib.metadata.version('openai'),
              timeout=60, sdk_max_retries=2,
              concurrency=int(os.environ['HALLUSION_JUDGE_CONCURRENCY']),
              scheduler='bounded threads; atomic ordered cache; v1',
              sampling='server defaults; no explicit temperature/top_p/max_tokens/thinking',
              result_sha256=hashlib.sha256((evaluation/'HallusionBench_result.json').read_bytes()).hexdigest(),
              official_utils_sha256=hashlib.sha256(source.encode()).hexdigest())
manifest = evaluation/'judge_config.json'
if manifest.exists():
    previous = json.loads(manifest.read_text())
    for field in ('model', 'base_url', 'result_sha256', 'official_utils_sha256'):
        if previous.get(field) != config[field]:
            raise RuntimeError(f'Existing judge cache differs in {field}; do not mix runs')
elif any(evaluation.glob('hallusion_output_*_model.json')):
    raise RuntimeError('Unidentified judge cache exists; inspect before reuse')
(evaluation/'utils.py.official').write_text(source, encoding='utf-8')
(evaluation/'utils.py').write_text(adapt_concurrent_utils(source), encoding='utf-8')
(evaluation/'evaluation.py').write_text(adapt_evaluation((d/'evaluation.py').read_text(encoding='utf-8')), encoding='utf-8')
manifest.write_text(json.dumps(config, indent=2)+'\n')
PY

cd "$EVAL"
"$PYTHON" -u evaluation.py \
  2>&1 | tee "evaluation-judge-api-$(date +%Y%m%d_%H%M%S).log"
"$PYTHON" "$KIT/summarize_hallusion_scores.py" --evaluation-dir "$EVAL"
date -Is > .judge_completed
echo "COMPLETED: $EVAL"
