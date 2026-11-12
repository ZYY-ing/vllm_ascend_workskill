#!/usr/bin/env python3
"""Pin a HF model file manifest, then verify local files offline (Python 3.10+)."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath


def member(root, name):
    parts = PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or not parts.parts:
        raise ValueError('Unsafe manifest path')
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Manifest member resolves outside local directory')
    return path


def digest(path, algorithm, git_blob=False):
    h = hashlib.new(algorithm)
    if git_blob:
        h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def capture(repo, revision, output):
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    files = []
    for entry in info.siblings:
        member(Path('.'), entry.rfilename)
        if entry.size is None:
            raise ValueError('Incomplete size metadata; cannot calculate repository size')
        lfs = entry.lfs
        sha = lfs.get('sha256') if isinstance(lfs, dict) else getattr(lfs, 'sha256', None)
        blob = getattr(entry, 'blob_id', None)
        files.append(dict(path=entry.rfilename, size=entry.size, sha256=sha,
                          git_blob_sha1=blob if not lfs else None))
    if not files or len({x['path'] for x in files}) != len(files):
        raise ValueError('Empty or duplicate manifest')
    result = dict(repo_id=repo, revision=info.sha, files=files,
                  total_bytes=sum(x['size'] for x in files))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(result, stream, ensure_ascii=False, indent=2)
    temporary.replace(output)
    return dict(revision=info.sha, files=len(files), bytes=result['total_bytes'])


def verify(manifest, local_dir, sizes_only=False):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if not data['files'] or len({x['path'] for x in data['files']}) != len(data['files']):
        raise ValueError('Empty or duplicate manifest')
    failures, unchecked = [], []
    complete_bytes = 0
    for entry in data['files']:
        path = member(local_dir, entry['path'])
        reason = None
        if not path.is_file():
            reason = 'missing'
        elif path.stat().st_size != entry['size']:
            reason = 'size_mismatch'
        elif not sizes_only:
            if entry.get('sha256'):
                if digest(path, 'sha256') != entry['sha256']:
                    reason = 'sha256_mismatch'
            elif entry.get('git_blob_sha1'):
                if digest(path, 'sha1', git_blob=True) != entry['git_blob_sha1']:
                    reason = 'git_blob_sha1_mismatch'
            else:
                unchecked.append(entry['path'])
        if reason:
            failures.append(dict(path=entry['path'], reason=reason))
        else:
            complete_bytes += entry['size']
    total = sum(x['size'] for x in data['files'])
    return dict(revision=data['revision'], expected_files=len(data['files']),
                valid_files=len(data['files'])-len(failures), valid_bytes=complete_bytes,
                total_bytes=total, failures=failures, unavailable_checksums=unchecked,
                verification='size_only' if sizes_only else 'checksums',
                completed=not sizes_only and not failures and not unchecked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('capture')
    make.add_argument('--repo', required=True)
    make.add_argument('--revision', default='main')
    make.add_argument('--output', required=True, type=Path)
    check = sub.add_parser('verify')
    check.add_argument('--manifest', required=True, type=Path)
    check.add_argument('--local-dir', required=True, type=Path)
    check.add_argument('--sizes-only', action='store_true')
    args = parser.parse_args()
    try:
        result = (capture(args.repo, args.revision, args.output) if args.command == 'capture'
                  else verify(args.manifest, args.local_dir, args.sizes_only))
    except Exception as exc:
        # Network exceptions may contain signed URLs or authentication headers.
        print(json.dumps(dict(error=type(exc).__name__,
                              hint='Check credentials, CA, metadata and local paths; redact debug logs.')))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == 'verify' and (result['failures'] or result['unavailable_checksums']):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
