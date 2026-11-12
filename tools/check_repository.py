#!/usr/bin/env python3
"""Check tracked skill resources without executing operational scripts or exposing secrets."""
import argparse
import ast
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def check(root, bash=None):
    errors, warnings = [], []
    # Walking this small source tree also checks newly added files before git add.
    files = [p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts
             and '__pycache__' not in p.parts and '.venv' not in p.parts]
    text_files = [p for p in files if p.suffix in ('.md', '.py', '.sh', '.ps1', '.yaml', '.json')
                  or p.name == '.gitignore']
    docs = scripts = blocks = links = 0
    bash = bash or shutil.which('bash')
    if not bash:
        warnings.append('Bash unavailable: Shell syntax was not checked; supply --bash')
    secret = re.compile(r'hf_[A-Za-z0-9]{15,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}'
                        r'|sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
                        r'|https?://[^\s/]+:[^\s/]+@|/home/z\d+|[A-Za-z0-9._+-]+@qq\.com')
    shell_sources = []
    for p in text_files:
        relative = p.relative_to(root).as_posix()
        try:
            s = p.read_text(encoding='utf-8')
        except UnicodeError:
            errors.append(relative + ': invalid UTF-8')
            continue
        for n, line in enumerate(s.splitlines(), 1):
            if secret.search(line):
                errors.append(f'{relative}:{n}: credential or personal identifier pattern; value hidden')
            for value in re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', line):
                try:
                    ip = ipaddress.ip_address(value)
                except ValueError:
                    continue
                documented = any(ip in ipaddress.ip_network(net) for net in
                                 ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24'))
                if not (ip.is_loopback or ip.is_unspecified or documented):
                    errors.append(f'{relative}:{n}: non-example IP address; value hidden')
        if p.suffix == '.py':
            scripts += 1
            try:
                ast.parse(s, filename=relative)
            except SyntaxError as exc:
                errors.append(f'{relative}:{exc.lineno}: Python syntax error')
        if p.suffix == '.sh':
            shell_sources.append((relative, s))
        if p.suffix == '.md':
            docs += 1
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', s):
                if '://' in target or target.startswith('#'):
                    continue
                local = target.split('#')[0]
                if local and not (p.parent / local).exists():
                    errors.append(f'{relative}: broken local link: {local}')
                links += 1
            for n, code in enumerate(re.findall(r'^```bash\n(.*?)^```', s, re.M | re.S), 1):
                shell_sources.append((relative + f':block{n}', code))
    skills = sorted((root / 'skills').glob('*/SKILL.md'))
    if not skills:
        errors.append('No skill entrypoints found')
    for p in skills:
        s = p.read_text(encoding='utf-8')
        front = re.match(r'^---\n(.*?)\n---\n', s, re.S)
        if not front:
            errors.append(str(p.relative_to(root)) + ': missing frontmatter')
            continue
        fields = dict(re.findall(r'^(name|description):\s*(.+)$', front[1], re.M))
        if fields.get('name') != p.parent.name or not fields.get('description'):
            errors.append(str(p.relative_to(root)) + ': name/description mismatch')
        if len(fields.get('description', '')) > 1024:
            errors.append(str(p.relative_to(root)) + ': description too long')
    manifest = json.loads((root / 'docs/migration-map.json').read_text(encoding='utf-8'))
    old = [x['old'] for x in manifest['files']]
    if len(old) != 35 or len(set(old)) != 35:
        errors.append('Migration inventory must cover all 35 original files exactly once')
    for item in manifest['files']:
        for dest in item['destinations']:
            if not (root / dest).is_file():
                errors.append('Missing migration destination: ' + dest)
    if bash:
        with tempfile.TemporaryDirectory(prefix='skill-shell-check-') as tmp:
            script = Path(tmp) / 'check.sh'
            for label, code in shell_sources:
                script.write_text(code, encoding='utf-8', newline='\n')
                r = subprocess.run([bash, '-n', script.as_posix()], capture_output=True, text=True)
                blocks += 1
                if r.returncode:
                    errors.append(label + ': Bash syntax error')
    return dict(skills=len(skills), markdown_files=docs, python_files=scripts, local_links=links,
                bash_sources_checked=blocks, original_files_mapped=len(old),
                errors=errors, warnings=warnings)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bash', help='Bash executable for script and documentation syntax checks')
    args = parser.parse_args()
    result = check(Path(__file__).resolve().parents[1], args.bash)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result['errors'] else 0)
