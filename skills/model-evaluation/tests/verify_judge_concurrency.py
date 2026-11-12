"""Offline tests: official prompts/labels, sparse resume, failure drain and order."""
import ast
from collections import Counter
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_evaluation import adapt_utils
from prepare_concurrent_judge import adapt_concurrent_utils, adapt_evaluation

ROOT = Path(__file__).resolve().parent


def run_tests(official):
    os.environ.update(HALLUSION_JUDGE_API_KEY='offline-placeholder',
                      HALLUSION_JUDGE_BASE_URL='https://offline.invalid/v1',
                      HALLUSION_JUDGE_MODEL='offline', HALLUSION_JUDGE_CONCURRENCY='4')
    # No real SDK is imported and no network access can occur.
    sdk = types.ModuleType('openai')
    sdk.OpenAI = lambda **kw: None
    sys.modules['openai'] = sdk
    if importlib.util.find_spec('tqdm') is None:
        module = types.ModuleType('tqdm')
        class Progress:
            def __init__(self, iterable=None, **kwargs):
                self.iterable = iterable
            def __iter__(self):
                return iter(self.iterable)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def update(self, amount):
                pass
        module.tqdm = Progress
        sys.modules['tqdm'] = module
    for name in ('numpy', 'prettytable'):
        if importlib.util.find_spec(name) is None:
            module = types.ModuleType(name)
            if name == 'prettytable':
                module.PrettyTable = object
            sys.modules[name] = module
    source = (official/'utils.py').read_text(encoding='utf-8')
    serial, parallel = {}, {}
    exec(compile(adapt_utils(source), '<serial>', 'exec'), serial)
    exec(compile(adapt_concurrent_utils(source), '<parallel>', 'exec'), parallel)
    data = [dict(category='VS', subcategory='map', set_id='0', figure_id=str(i//4),
                 question_id=str(i%4), visual_input='0' if i < 4 else '1',
                 question=f'question {i}', gt_answer_details='yes',
                 model_prediction=f'answer {i}') for i in range(12)]
    entry = 'gpt4v_output_gpt_check'
    reports = {}
    with tempfile.TemporaryDirectory() as tmp:
        calls = [[], []]
        active = 0
        peak = 0
        lock = threading.Lock()

        def request(which):
            def call(**kwargs):
                nonlocal active, peak
                prompt = kwargs['messages'][0]['content']
                with lock:
                    calls[which].append(prompt)
                    active += 1
                    peak = max(peak, active)
                try:
                    time.sleep(0.005 * (1 + len(prompt) % 7))
                    text = ('same' if 'response1:' in prompt else
                            ['correct', 'incorrect', 'unclear'][len(prompt) % 3])
                    return {'choices': [{'message': {'content': text}}]}
                finally:
                    with lock:
                        active -= 1
            return call

        outputs = []
        for which, namespace in enumerate((serial, parallel)):
            namespace['_judge_request'] = request(which)
            path = str(Path(tmp)/f'{which}.json')
            result = namespace['evaluate_by_chatgpt'](deepcopy(data), 'model_prediction', entry,
                                                     load_json=True, save_json_path=path)
            result = namespace['check_same_by_chatgpt'](result, 'model_prediction',
                                                       load_json=True, save_json_path=path)
            outputs.append(result)
        assert outputs[0] == outputs[1]
        assert Counter(calls[0]) == Counter(calls[1])
        assert peak == 4
        reports['official_prompts_labels_order_and_peak4'] = 'PASS'
        before = len(calls[1])
        parallel['evaluate_by_chatgpt'](deepcopy(data), 'model_prediction', entry,
                                       load_json=True, save_json_path=str(Path(tmp)/'1.json'))
        assert len(calls[1]) == before
        reports['completed_cache_zero_requests'] = 'PASS'
        partial_same = deepcopy(outputs[1])
        for row in partial_same[3:]:
            row.pop('same')
        same_path = Path(tmp)/'same.json'
        same_path.write_text(json.dumps(partial_same))
        before_same = len(calls[1])
        resumed_same = parallel['check_same_by_chatgpt'](deepcopy(partial_same), 'model_prediction',
                                                       load_json=True, save_json_path=str(same_path))
        assert resumed_same == outputs[1]
        assert len(calls[1])-before_same == 9
        reports['consistency_resume_only_missing9'] = 'PASS'
        os.environ['HALLUSION_JUDGE_CONCURRENCY'] = '1'
        one = parallel['evaluate_by_chatgpt'](deepcopy(data), 'model_prediction', entry,
                                            save_json_path=str(Path(tmp)/'c1.json'))
        assert one == [{k: v for k, v in row.items() if k != 'same'} for row in outputs[0]]
        os.environ['HALLUSION_JUDGE_CONCURRENCY'] = '4'
        reports['concurrency1_fallback'] = 'PASS'
        before = len(calls[1])

        # Simulate an out-of-order partial cache left by a failed run.
        sparse = [outputs[1][i].copy() for i in (1, 4, 8)]
        for row in sparse:
            row.pop('same')
        path = Path(tmp)/'sparse.json'
        path.write_text(json.dumps(sparse))
        resumed = parallel['evaluate_by_chatgpt'](deepcopy(data), 'model_prediction', entry,
                                                load_json=True, save_json_path=str(path))
        assert len(calls[1])-before == 9
        assert [r['question'] for r in resumed] == [r['question'] for r in data]
        reports['sparse_cache_resume_exact_missing9'] = 'PASS'
        sparse[0]['model_prediction'] = 'mismatch'
        path.write_text(json.dumps(sparse))
        try:
            parallel['evaluate_by_chatgpt'](deepcopy(data), 'model_prediction', entry,
                                           load_json=True, save_json_path=str(path))
            raise AssertionError('Mismatch accepted')
        except ValueError:
            pass
        reports['cache_mismatch_rejected'] = 'PASS'

        from judge_concurrency import run_stage
        started = []
        def fail_worker(row):
            started.append(row['question'])
            if row['question'] == 'question 0':
                raise RuntimeError('offline simulated 401')
            time.sleep(0.05)
            row[entry] = '1'
            return row
        path = Path(tmp)/'failed.json'
        try:
            run_stage(data, fail_worker, entry, str(path), True, entry)
            raise AssertionError('Failure swallowed')
        except RuntimeError as exc:
            assert '401' in str(exc)
        assert len(started) == 4
        assert len(json.loads(path.read_text())) == 3
        reports['failure_stops_refill_drains_saves3'] = 'PASS'
        calls_before = len(calls[1])
        parallel['evaluate_by_chatgpt'](deepcopy(data), 'model_prediction', entry,
                                       load_json=True, save_json_path=str(path))
        assert len(calls[1])-calls_before == 9
        reports['failed_run_resumes_only_missing'] = 'PASS'

    evaluation = (official/'evaluation.py').read_text(encoding='utf-8')
    transformed = ast.parse(adapt_evaluation(evaluation))
    assert not any(isinstance(n, ast.Try) for n in ast.walk(transformed))
    reports['removed_whole_stage_retry'] = 'PASS'
    os.environ.pop('HALLUSION_JUDGE_API_KEY', None)
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    run_tests(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT)
