"""Prepare a fresh official evaluator with environment-based modern OpenAI API calls."""
import argparse
import ast
from datetime import datetime
import os
import re
from pathlib import Path
import shutil
import textwrap


def adapt_utils(source):
    lines = source.splitlines(keepends=True)
    edits = []
    tree = ast.parse(source)
    # Remove the legacy apikey.txt/default-key loader, without reading any key.
    for node in tree.body:
        if isinstance(node, ast.Try):
            segment = ast.get_source_segment(source, node)
            if 'api_key' in segment:
                edits.append((node.lineno-1, node.end_lineno, ''))
    loops = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.While) and isinstance(node.test, ast.Constant)
                and node.test.value is True and len(node.body) == 1
                and isinstance(node.body[0], ast.Try)):
            continue
        attempt = node.body[0]
        if 'openai.ChatCompletion.create' not in ast.get_source_segment(source, attempt):
            continue
        body = ''.join(''.join(lines[s.lineno-1:s.end_lineno])
                       for s in attempt.body if not isinstance(s, ast.Break))
        body = textwrap.indent(textwrap.dedent(body), ' '*node.col_offset)
        edits.append((node.lineno-1, node.end_lineno, body))
        loops += 1
    assert loops == 2, 'Official utils.py changed; inspect before adapting'
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    source = ''.join(lines).replace('openai.ChatCompletion.create(', '_judge_request(')
    source = re.sub(r'(?m)^[ \t]*api_key=api_key,[ \t]*\r?\n', '', source)
    helper = '''
_JUDGE = openai.OpenAI(
    api_key=os.environ['HALLUSION_JUDGE_API_KEY'],
    base_url=os.environ['HALLUSION_JUDGE_BASE_URL'],
    timeout=60, max_retries=2,
)


def _judge_request(**kwargs):
    kwargs.pop('request_timeout', None)
    kwargs['model'] = os.environ['HALLUSION_JUDGE_MODEL']
    return _JUDGE.chat.completions.create(**kwargs).model_dump()


'''
    source = source.replace('def get_image_file_location(', helper+'def get_image_file_location(', 1)
    ast.parse(source)
    return source


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--official', required=True)
    ap.add_argument('--run', required=True)
    args = ap.parse_args()
    official, run = Path(args.official), Path(args.run).resolve()
    result = run/'HallusionBench_result.json'
    assert result.is_file(), 'Complete inference first'
    target = run/('evaluation-'+datetime.now().strftime('%Y%m%d_%H%M%S')+'-'+str(os.getpid()))
    target.mkdir()
    shutil.copy2(result, target/result.name)
    shutil.copy2(official/'evaluation.py', target/'evaluation.py')
    source = (official/'utils.py').read_text(encoding='utf-8')
    (target/'utils.py.official').write_text(source, encoding='utf-8')
    (target/'utils.py').write_text(adapt_utils(source), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
