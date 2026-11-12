"""Offline checks for the shell inference entrypoint and optional judge smoke helper."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import types
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def check_auth():
    spec = importlib.util.spec_from_file_location('judge_auth_check', SCRIPTS / 'check_judge_auth.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    class APIError(Exception):
        def __init__(self, status):
            self.status_code = status
    class Client:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=self)
        def create(self, **kw):
            calls.append(kw)
            if os.environ['HALLUSION_JUDGE_MODEL'] == 'unauthorized':
                raise APIError(401)
            content = '' if os.environ['HALLUSION_JUDGE_MODEL'] == 'empty' else 'OK'
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])
    sdk = types.ModuleType('openai')
    sdk.OpenAI, sdk.APIStatusError = Client, APIError
    env = dict(HALLUSION_JUDGE_BASE_URL='https://offline.invalid/v1',
               HALLUSION_JUDGE_MODEL='offline', HALLUSION_JUDGE_API_KEY='offline-placeholder')
    with patch.dict(sys.modules, {'openai': sdk}), patch.dict(os.environ, env, clear=True):
        assert module.main() == 0
        assert set(calls[0]) == {'model', 'messages'}, 'Smoke must not silently override model sampling'
        os.environ['HALLUSION_JUDGE_MODEL'] = 'unauthorized'
        assert module.main() == 11
        os.environ['HALLUSION_JUDGE_MODEL'] = 'empty'
        assert module.main() == 14
        os.environ['HALLUSION_JUDGE_BASE_URL'] = 'https://offline.invalid/v1?key=offline-placeholder'
        before = len(calls)
        assert module.main() == 2 and len(calls) == before
    return 'PASS: stub SDK only; no paid API'


def check_runner(bash):
    state = {'calls': []}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def reply(self, payload):
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            self.reply({'data': [{'id': 'mock-model'}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['calls'].append(body)
            if body['model'] == 'fail-model':
                self.send_error(503)
                return
            self.reply({'choices': [{'message': {'content': 'reasoning</think:opensource>yes'},
                                     'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 20}})
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    reports = []
    try:
        with tempfile.TemporaryDirectory(prefix='hallusion-entrypoint-') as tmp:
            home = Path(tmp)
            official = home / 'HallusionBench'
            official.mkdir()
            rows = [dict(category='VS', subcategory='map', set_id='0', figure_id='0',
                         question_id=str(i), visual_input=0, question=f'q{i}', gt_answer='private-reference')
                    for i in range(4)]
            (official / 'HallusionBench.json').write_text(json.dumps(rows))
            base = [bash, str(SCRIPTS / 'run_full.sh'), '--home', str(home), '--python', sys.executable,
                    '--api', f'http://127.0.0.1:{server.server_port}/v1', '--model', 'mock-model']
            env = os.environ.copy()
            # The test is independent of any caller's actual runtime/credentials.
            for k in list(env):
                if k.startswith('HALLUSION_') or k == 'HY4_API_KEY':
                    env.pop(k)
            env.update(HALLUSION_LIMIT='4', HALLUSION_CONCURRENCY='1')
            def run(options, expected=0):
                r = subprocess.run(base + options, env=env, capture_output=True, text=True, timeout=30)
                assert r.returncode == expected, (r.returncode, r.stdout, r.stderr)
            run(['--check-only'])
            assert not state['calls']
            assert not (home / 'outputs').exists()
            reports.append('check_only_zero_inference')
            out = home / 'run'
            run(['--limit', '2', '--concurrency', '2', '--max_tokens', '99', '--temperature', '0.8',
                 '--no_skip_special_tokens', '--output', str(out)])
            assert len(state['calls']) == 2
            for body in state['calls']:
                assert body['max_tokens'] == 99 and body['temperature'] == 0.8
                assert body['skip_special_tokens'] is False
                assert 'private-reference' not in json.dumps(body)
            report = json.loads((out / 'integrity_report.json').read_text())
            assert report['samples'] == 2 and report['scope'] == 'first_n_subset'
            reports.append('cli_over_env_aliases_sampling_and_subset_integrity')
            before = len(state['calls'])
            run(['--output', str(out)], expected=2)
            assert len(state['calls']) == before
            reports.append('existing_output_rejected_before_requests')
            run(['--concurrency', '0'], expected=2)
            reports.append('invalid_concurrency_rejected')
            before = len(state['calls'])
            rejected = subprocess.run(base + ['--api', 'https://offline.invalid/v1?key=offline-placeholder'],
                                      env=env, capture_output=True, text=True, timeout=30)
            assert rejected.returncode != 0 and len(state['calls']) == before
            assert 'offline-placeholder' not in rejected.stdout + rejected.stderr
            reports.append('credential_url_rejected_without_echo_or_network')
            # Switch the mock /models response for an actual inference failure case.
            original = Handler.do_GET
            Handler.do_GET = lambda self: self.reply({'data': [{'id': 'fail-model'}]})
            failed = home / 'failed'
            r = subprocess.run(base + ['--model', 'fail-model', '--concurrency', '1', '--output', str(failed)],
                               env=env, capture_output=True, text=True, timeout=30)
            Handler.do_GET = original
            assert r.returncode != 0
            assert (failed / 'failure.json').exists()
            assert not (failed / 'HallusionBench_result.json').exists()
            assert not (failed / 'evaluation').exists()
            reports.append('failure_nonzero_partial_retained_no_judge')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    return reports


if __name__ == '__main__':
    bash = sys.argv[1] if len(sys.argv) > 1 else shutil.which('bash')
    if not bash:
        raise SystemExit('Bash is required; pass its executable path as the first argument')
    result = {'inference_entrypoint': check_runner(bash), 'judge_auth': check_auth()}
    print(json.dumps(result, indent=2))
