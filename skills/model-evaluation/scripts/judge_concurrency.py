"""Bounded judge scheduling; only the coordinator writes atomic ordered caches."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
import json
import os
from pathlib import Path
from tqdm import tqdm

FIELDS = ('category', 'subcategory', 'set_id', 'figure_id', 'question_id')


def identity(row):
    return tuple(str(row[k]) for k in FIELDS)


def atomic_save(path, rows):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run_stage(data, worker, field, path, load_json, correctness_entry):
    concurrency = int(os.environ.get('HALLUSION_JUDGE_CONCURRENCY', '4'))
    if not 1 <= concurrency <= 64:
        raise ValueError('HALLUSION_JUDGE_CONCURRENCY must be between 1 and 64')
    rows = deepcopy(data)
    positions = {identity(row): i for i, row in enumerate(rows)}
    if len(positions) != len(rows):
        raise ValueError('Duplicate input question ID')
    ignored = {correctness_entry, 'same', 'correct'}
    if load_json and Path(path).exists():
        cached = json.loads(Path(path).read_text(encoding='utf-8'))
        seen = set()
        for saved in cached:
            key = identity(saved)
            if key in seen or key not in positions:
                raise ValueError('Duplicate or unknown question in judge cache')
            seen.add(key)
            row = rows[positions[key]]
            if {k: v for k, v in saved.items() if k not in ignored} != {
                    k: v for k, v in row.items() if k not in ignored}:
                raise ValueError(f'Judge cache input differs: {key}')
            for name, allowed in ((correctness_entry, {'0', '1', '2'}), ('same', {'0', '1'})):
                if name in saved:
                    if str(saved[name]) not in allowed:
                        raise ValueError(f'Invalid cached {name}: {key}')
                    row[name] = str(saved[name])
    if field == 'same' and any(correctness_entry not in row for row in rows):
        raise ValueError('Correctness must complete before consistency')
    pending = iter(i for i, row in enumerate(rows) if field not in row)
    label = f"{rows[0]['category'] if rows else ''} {field} C={concurrency}"
    completed = sum(field in row for row in rows)
    failure = None

    def save():
        atomic_save(path, [row for row in rows if correctness_entry in row])

    with ThreadPoolExecutor(max_workers=concurrency) as pool, tqdm(
            total=len(rows), initial=completed, desc=label, unit='question') as bar:
        active = {}

        def fill():
            while len(active) < concurrency:
                index = next(pending, None)
                if index is None:
                    break
                active[pool.submit(worker, deepcopy(rows[index]))] = index

        fill()
        try:
            while active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    index = active.pop(future)
                    try:
                        rows[index] = future.result()
                        save()
                        bar.update(1)
                    except Exception as exc:
                        if failure is None:
                            failure = exc
                if failure is None:
                    fill()
        except BaseException as exc:
            failure = exc
            # Drain requests already sent; never discard successful billed results.
            for future, index in active.items():
                try:
                    rows[index] = future.result()
                    save()
                    bar.update(1)
                except Exception:
                    pass
        if failure is not None:
            raise failure
    save()
    return rows
