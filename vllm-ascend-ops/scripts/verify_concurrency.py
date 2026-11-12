"""Local mock-HTTP integration checks. Does not contact HY4 or a judge API."""
import base64
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent


def exercise(concurrency, fail=False, limit=0):
    state = dict(active=0, peak=0, calls=[], payloads=[], errors=[])
    lock = threading.Lock()
    first_wave = threading.Barrier(concurrency)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            data = json.dumps({'data': [{'id': 'hy4'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            question = body['messages'][0]['content'][-1]['text']
            index = int(question[1:])
            with lock:
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
                state['calls'].append(index)
                state['payloads'].append((index, body))
            try:
                if index < concurrency:
                    first_wave.wait(timeout=5)
                if fail and index == 0:
                    self.send_error(503, 'mock overload')
                    return
                time.sleep(0.15 if fail or index == 0 else 0.025)
                response = dict(choices=[dict(message=dict(content=f'thinking</think:opensource>answer-{index}'),
                                             finish_reason='stop')],
                                usage=dict(prompt_tokens=10+index, completion_tokens=20+index))
                data = json.dumps(response).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                with lock:
                    state['active'] -= 1

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='hallusion-concurrency-') as temporary:
            root = Path(temporary)
            (root/'image.png').write_bytes(b'mock-image-bytes')
            rows = [dict(category='VS', subcategory='map', set_id='0', figure_id=str(i),
                         question_id=str(i), visual_input=i % 3, filename='image.png',
                         question=f'q{i}', gt_answer='yes') for i in range(12)]
            dataset = root/'data.json'
            dataset.write_text(json.dumps(rows), encoding='utf-8')
            out = root/'run'
            command = [sys.executable, '-B', str(HERE/'run_hallusionbench_hy4.py'),
                       '--data', str(dataset), '--root', str(root),
                       '--api', f'http://127.0.0.1:{server.server_port}/v1', '--model', 'hy4',
                       '--output', str(out), '--concurrency', str(concurrency),
                       '--limit', str(limit),
                       '--max-tokens', '102400', '--temperature', '0.8',
                       '--top-k', '15', '--top-p', '0.95', '--repetition-penalty', '1.0',
                       '--no-skip-special-tokens', '--reasoning-effort', 'high']
            process = subprocess.run(command, capture_output=True, text=True, timeout=20)
            raw = [json.loads(line) for line in (out/'responses.jsonl').read_text().splitlines()]
            assert state['peak'] <= concurrency, state
            assert max(Counter(state['calls']).values()) == 1, 'Duplicate HTTP request'
            for index, body in state['payloads']:
                assert body['model'] == 'hy4' and body['stream'] is False
                assert body['max_tokens'] == 102400 and body['temperature'] == 0.8
                assert body['top_k'] == 15 and body['top_p'] == 0.95
                assert body['repetition_penalty'] == 1.0 and body['skip_special_tokens'] is False
                assert body['chat_template_kwargs'] == {'reasoning_effort': 'high'}
                content = body['messages'][0]['content']
                assert len(content) == (1 if rows[index]['visual_input'] == 0 else 2)
                if rows[index]['visual_input']:
                    assert base64.b64decode(content[0]['image_url']['url'].split(',')[1]) == b'mock-image-bytes'
            if fail:
                assert process.returncode != 0
                assert not (out/'HallusionBench_result.json').exists()
                assert not (out/'summary.json').exists()
                failure = json.loads((out/'failure.json').read_text())
                assert failure['errors'][0]['index'] == 0
                assert set(state['calls']) == set(range(concurrency)), state['calls']
                assert len(raw) == concurrency-1, 'Already-running successes must be preserved'
                assert failure['completed'] == concurrency
            else:
                assert process.returncode == 0, process.stderr
                assert state['peak'] == concurrency, state
                selected = min(limit, 12) if limit else 12
                assert sorted(state['calls']) == list(range(selected))
                result = json.loads((out/'HallusionBench_result.json').read_text())
                assert [r['model_prediction'] for r in result] == [f'answer-{i}' for i in range(selected)]
                if concurrency > 1:
                    assert [r['index'] for r in raw] != list(range(selected)), 'Fixture should finish out of order'
                check = [sys.executable, '-B', str(HERE/'check_results.py'), '--data', str(dataset), '--run', str(out)]
                checked = subprocess.run(check, capture_output=True, text=True, timeout=10)
                assert checked.returncode == 0, checked.stderr
                report = json.loads((out/'integrity_report.json').read_text())
                assert report['samples'] == selected and report['finish_reasons'] == {'stop': selected}
                assert report['dataset_samples'] == 12
                assert report['scope'] == ('full' if selected == 12 else 'first_n_subset')
                preflight = subprocess.run([sys.executable, '-B', str(HERE/'preflight.py'),
                    '--data', str(dataset), '--root', str(root), '--api',
                    f'http://127.0.0.1:{server.server_port}/v1', '--model', 'hy4', '--limit', str(limit)],
                    capture_output=True, text=True, timeout=10)
                assert preflight.returncode == 0, preflight.stderr
                assert json.loads(preflight.stdout)['samples'] == selected
                # Ensure the updated checker does not merely ignore journal ordering/identity errors.
                raw[0]['index'] = raw[1]['index']
                (out/'responses.jsonl').write_text('\n'.join(json.dumps(r) for r in raw)+'\n')
                rejected = subprocess.run(check, capture_output=True, text=True, timeout=10)
                assert rejected.returncode != 0, 'Duplicate raw indices must be rejected'
            return dict(concurrency=concurrency, limit=limit, failure_case=fail, maximum_observed_inflight=state['peak'],
                        requests_received=len(state['calls']), passed=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    results = [exercise(1), exercise(4), exercise(4, fail=True), exercise(4, limit=5), exercise(4, limit=20)]
    report = dict(scope='localhost mock HTTP only; no real model performance/accuracy claim', cases=results)
    (HERE/'verification_results.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
