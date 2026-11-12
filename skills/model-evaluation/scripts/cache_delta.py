#!/usr/bin/env python3
"""Measure prefix-cache counter deltas for one model, by DP engine."""
import argparse
import json
import math
import re
from pathlib import Path


def read(path, model):
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.match(r'vllm:prefix_cache_(hits|queries)_total(?:\{([^}]*)\})?\s+(\S+)', line)
        if not match:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', match[2] or ''))
        if labels.get('model_name', model) != model:
            continue
        value = float(match[3])
        if not math.isfinite(value) or value < 0:
            raise ValueError('Invalid counter value')
        engine = labels.get('engine', 'unspecified')
        data = result.setdefault(engine, {})
        data[match[1]] = data.get(match[1], 0) + value
    if not result:
        raise ValueError('No matching prefix_cache counters; check model and metric names')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    before, after = read(args.before, args.model), read(args.after, args.model)
    if set(before) != set(after):
        raise ValueError('Engine sets changed; snapshots cannot be compared')
    engines = {}
    for engine, data in after.items():
        if set(data) != {'hits', 'queries'} or set(before[engine]) != {'hits', 'queries'}:
            raise ValueError('Both hits and queries counters are required per engine')
        hits = data['hits'] - before[engine]['hits']
        queries = data['queries'] - before[engine]['queries']
        if hits < 0 or queries < 0 or hits > queries:
            raise ValueError('Counters reset or have incompatible semantics; ratio is invalid')
        engines[engine] = dict(cached_tokens_delta=hits, queried_tokens_delta=queries,
                               hit_ratio=hits / queries if queries else None)
    hits = sum(item['cached_tokens_delta'] for item in engines.values())
    queries = sum(item['queried_tokens_delta'] for item in engines.values())
    result = dict(engines=engines, total_cached_tokens_delta=hits,
                  total_queried_tokens_delta=queries,
                  total_hit_ratio=hits / queries if queries else None,
                  note='Only attributable to this run without overlapping requests or counter resets.')
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.write_text(payload, encoding='utf-8')
    print(payload)


if __name__ == '__main__':
    main()
