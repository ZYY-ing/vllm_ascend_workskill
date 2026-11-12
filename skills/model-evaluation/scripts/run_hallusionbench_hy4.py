"""Bounded-concurrency OpenAI-compatible HallusionBench inference; standard library only."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import time
import base64
import json
import mimetypes
import os
from pathlib import Path
import urllib.request


def image_path(root, row):
    p = Path(root) / row["filename"]
    if not p.is_file():
        p = Path(root) / "hallusion_bench" / row["filename"]
    if not p.is_file():
        raise FileNotFoundError(p)
    return p


def request_one(args, row):
    """Each worker owns its request/opener and never writes shared files."""
    started = time.monotonic()
    content = []
    if int(row["visual_input"]) != 0:
        p = image_path(args.root, row)
        mime = mimetypes.guess_type(str(p))[0] or "image/png"
        uri = "data:" + mime + ";base64," + base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": uri}})
    content.append({"type": "text", "text": row["question"]})
    body = dict(model=args.model, messages=[dict(role="user", content=content)],
                max_tokens=args.max_tokens, temperature=args.temperature, stream=False)
    # Omit unspecified extension fields to preserve previous server defaults.
    for key in ("top_k", "top_p", "repetition_penalty", "skip_special_tokens"):
        if (value := getattr(args, key)) is not None:
            body[key] = value
    if args.reasoning_effort is not None:
        body["chat_template_kwargs"] = {"reasoning_effort": args.reasoning_effort}
    headers = {"Content-Type": "application/json"}
    if os.environ.get("HY4_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["HY4_API_KEY"]
    request = urllib.request.Request(args.api.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
    # Direct access to the local cluster API; do not use public HTTP proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=args.request_timeout) as response:
        raw = json.load(response)
    return raw, time.monotonic() - started


def prediction_from(raw, index):
    choice = raw["choices"][0]
    text = choice["message"].get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"Empty final answer at sample {index}")
    for marker in ("</think:opensource>", "</think>"):
        if marker in text:
            text = text.rsplit(marker, 1)[1].strip()
    if not text or "<think" in text:
        raise ValueError(f"Incomplete/unrecognized reasoning output at sample {index}")
    return text


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_requests(args, rows, out):
    """Bounded replenishment; main thread is the sole result writer."""
    count = len(rows)
    results = [None] * count
    tokens, prompt_tokens, reasons = [], [], []
    failures = []
    next_index = completed = 0
    started = time.monotonic()
    with (out / "responses.jsonl").open("w", encoding="utf-8") as log:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            pending = {}
            while pending or (next_index < count and not failures):
                while not failures and next_index < count and len(pending) < args.concurrency:
                    i = next_index
                    pending[pool.submit(request_one, args, rows[i])] = i
                    next_index += 1
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    i = pending.pop(future)
                    completed += 1
                    try:
                        raw, duration = future.result()
                        # Completion-order journal, keyed by original dataset index.
                        log.write(json.dumps(dict(index=i, sample=rows[i], response=raw,
                                                  elapsed_seconds=duration), ensure_ascii=False) + "\n")
                        log.flush()
                        text = prediction_from(raw, i)
                        results[i] = dict(rows[i], model_prediction=text)
                        usage = raw.get("usage", {})
                        n = usage.get("completion_tokens")
                        p = usage.get("prompt_tokens")
                        tokens.append(n if isinstance(n, int) else None)
                        prompt_tokens.append(p if isinstance(p, int) else None)
                        reasons.append(raw["choices"][0].get("finish_reason"))
                        write_json(out / "partial_results.json", [r for r in results if r is not None])
                        print(f"{completed}/{count} index={i} completion_tokens={n} "
                              f"finish_reason={reasons[-1]} elapsed={time.monotonic()-started:.1f}s "
                              f"concurrency={args.concurrency}", flush=True)
                    except Exception as error:
                        # Do not blindly retry a request the server may already have executed.
                        failures.append(dict(index=i, error_type=type(error).__name__, error=str(error)))
                        write_json(out / "failure.json", dict(errors=failures, submitted=next_index,
                                   completed=completed, total=count))
                        print(f"FAILED index={i}: {type(error).__name__}; stop submitting, "
                              "drain in-flight requests", flush=True)
                # On error, no new work is submitted; existing futures still get journaled.
    if failures:
        write_json(out / "failure.json", dict(errors=failures, submitted=next_index,
                   completed=completed, succeeded=sum(r is not None for r in results), total=count))
        raise RuntimeError("Inference failed; inspect failure.json and responses.jsonl; no final result published")
    assert all(r is not None for r in results)
    return results, tokens, prompt_tokens, reasons, time.monotonic() - started


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="Official HallusionBench.json")
    ap.add_argument("--root", required=True, help="Directory containing hallusion_bench/")
    ap.add_argument("--api", required=True, help="OpenAI-compatible API base URL ending in /v1")
    ap.add_argument("--model", required=True, help="Served model name")
    ap.add_argument("--output", required=True, help="New experiment directory")
    ap.add_argument("--limit", type=int, help="Run the first N samples; omit or use 0 for the full dataset")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-k", type=int, help="vLLM top_k; -1 disables top-k filtering")
    ap.add_argument("--top-p", type=float)
    ap.add_argument("--repetition-penalty", type=float)
    ap.add_argument("--skip-special-tokens", action=argparse.BooleanOptionalAction, default=None,
                    help="Use --no-skip-special-tokens to preserve special tokens")
    ap.add_argument("--reasoning-effort", choices=("high", "max", "no_think"),
                    help="HY4 template setting; verify support in the deployed checkpoint")
    ap.add_argument("--concurrency", type=int, default=1, help="Maximum in-flight requests")
    ap.add_argument("--request-timeout", type=float, default=1200,
                    help="HTTP socket-operation timeout in seconds; not a total wall-clock deadline")
    args = ap.parse_args()
    if args.concurrency < 1:
        ap.error("--concurrency must be positive")
    if not 0 < args.request_timeout < float("inf"):
        ap.error("--request-timeout must be finite and positive")
    if args.top_k is not None and args.top_k != -1 and args.top_k < 1:
        ap.error("--top-k must be -1 or a positive integer")
    if args.top_p is not None and not 0 < args.top_p <= 1:
        ap.error("--top-p must be in (0, 1]")
    if args.repetition_penalty is not None and not 0 < args.repetition_penalty < float("inf"):
        ap.error("--repetition-penalty must be finite and positive")
    rows = json.loads(Path(args.data).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Expected official dataset JSON array")
    if args.limit is not None and args.limit < 0:
        ap.error("--limit must be 0 (full dataset) or a positive integer")
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        raise ValueError("Empty dataset")
    # Validate every required image before sending any requests.
    for row in rows:
        if int(row["visual_input"]) != 0:
            image_path(args.root, row)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    (out / "config.json").write_text(json.dumps(vars(args), indent=2), encoding="utf-8")
    results, tokens, prompt_tokens, reasons, elapsed = run_requests(args, rows, out)
    known = [n for n in tokens if n is not None]
    known_prompt = [n for n in prompt_tokens if n is not None]
    summary = dict(samples=len(rows), concurrency=args.concurrency,
                   elapsed_seconds=elapsed, requests_per_second=len(rows)/elapsed,
                   output_tokens_per_second=sum(known)/elapsed if len(known)==len(rows) else None, token_usage_coverage=len(known),
                   prompt_token_usage_coverage=len(known_prompt),
                   avg_prompt_token=sum(known_prompt)/len(known_prompt) if len(known_prompt)==len(rows) else None,
                   avg_completion_token=sum(known)/len(known) if len(known)==len(rows) else None,
                   length_truncated=sum(r=="length" for r in reasons),
                   note="Inference only; accuracy requires the matching evaluator")
    (out / "HallusionBench_result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
