"""Validate all questions/images and the deployed API without running inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from run_hallusionbench_hy4 import image_path

FIELDS = ('category', 'subcategory', 'set_id', 'figure_id', 'question_id')


def identity(row):
    return tuple(str(row[k]) for k in FIELDS)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True)
    ap.add_argument('--root', required=True)
    ap.add_argument('--api', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--limit', type=int, default=0, help='0=all; positive N=first N samples')
    args = ap.parse_args()
    if args.limit < 0:
        ap.error('--limit must be nonnegative')
    data = Path(args.data)
    rows = json.loads(data.read_text(encoding='utf-8'))
    assert rows and isinstance(rows, list), 'Expected nonempty official JSON array'
    assert len({identity(r) for r in rows}) == len(rows), 'Duplicate question IDs'
    dataset_samples = len(rows)
    if args.limit:
        rows = rows[:args.limit]
    counts = Counter(int(r['visual_input']) for r in rows)
    assert set(counts) <= {0, 1, 2}, counts
    paths = set()
    for row in rows:
        assert row['question'].strip(), identity(row)
        if int(row['visual_input']) != 0:
            paths.add(image_path(args.root, row).resolve())
    opener = build_opener(ProxyHandler({}))
    api = args.api.rstrip('/')
    with opener.open(api.removesuffix('/v1') + '/health', timeout=15) as response:
        assert response.status == 200
    with opener.open(api + '/models', timeout=15) as response:
        models = json.load(response)['data']
    model = next(m for m in models if m['id'] == args.model)
    print(json.dumps(dict(samples=len(rows), dataset_samples=dataset_samples, limit=args.limit, visual_input_counts=dict(counts),
                          unique_images=len(paths), missing_images=0,
                          data_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                          api=args.api, model=model), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
