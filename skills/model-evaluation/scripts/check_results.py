"""Check completed inference IDs, answers, usage, truncations and token quantiles."""
import argparse
from collections import Counter
import json
from pathlib import Path
from preflight import identity


def stats(values):
    values = sorted(values)
    if not values:
        return None
    return dict(mean=sum(values)/len(values),
                p50=values[round((len(values)-1)*0.50)],
                p95=values[round((len(values)-1)*0.95)],
                p99=values[round((len(values)-1)*0.99)], maximum=max(values))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True)
    ap.add_argument('--run', required=True)
    ap.add_argument('--limit', type=int, default=None, help='Defaults to the limit recorded in RUN/config.json')
    args = ap.parse_args()
    run = Path(args.run)
    expected = json.loads(Path(args.data).read_text())
    dataset_samples = len(expected)
    config_path = run/'config.json'
    config = json.loads(config_path.read_text()) if config_path.is_file() else {}
    limit = args.limit if args.limit is not None else (config.get('limit') or 0)
    if type(limit) is not int or limit < 0:
        ap.error('limit must be a nonnegative integer')
    if limit:
        expected = expected[:limit]
    results = json.loads((run/'HallusionBench_result.json').read_text())
    raw = [json.loads(line) for line in (run/'responses.jsonl').read_text().splitlines()]
    assert not (run/'failure.json').exists(), 'Run has failure.json'
    assert len(expected) == len(results) == len(raw), 'Incomplete inference'
    ids = [identity(r) for r in results]
    assert len(set(ids)) == len(ids), 'Duplicate result IDs'
    assert set(ids) == {identity(r) for r in expected}, 'Result IDs differ from dataset'
    # Old serial and new completion-order journals share the same index field.
    indices = [r.get('index') for r in raw]
    assert all(type(i) is int for i in indices), 'Invalid raw index'
    assert sorted(indices) == list(range(len(expected))), 'Missing/duplicate/out-of-range raw index'
    raw.sort(key=lambda r: r['index'])
    assert [identity(r['sample']) for r in raw] == ids, 'Raw/result ID mismatch'
    for original, result in zip(raw, results):
        text = original['response']['choices'][0]['message'].get('content')
        assert isinstance(text, str), 'Invalid raw answer'
        for marker in ('</think:opensource>', '</think>'):
            if marker in text:
                text = text.rsplit(marker, 1)[1].strip()
        assert result['model_prediction'] == text, 'Raw/final prediction mismatch'
    assert all(r['model_prediction'].strip() for r in results), 'Empty final answer'
    for source, result in zip(expected, results):
        assert all(result.get(k) == v for k, v in source.items()), 'Dataset row changed'
    reasons = Counter(r['response']['choices'][0].get('finish_reason') for r in raw)
    tokens = {key: [r['response'].get('usage', {}).get(key) for r in raw]
              for key in ('prompt_tokens', 'completion_tokens')}
    report = dict(samples=len(results), dataset_samples=dataset_samples, limit=limit,
                  scope='full' if len(expected)==dataset_samples else 'first_n_subset',
                  finish_reasons=dict(reasons))
    for key, values in tokens.items():
        known = [v for v in values if isinstance(v, int)]
        report[key] = dict(coverage=len(known), stats=stats(known) if len(known)==len(raw) else None)
    report['note'] = 'Inference integrity only; accuracy requires independent judge evaluation.'
    (run/'integrity_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
