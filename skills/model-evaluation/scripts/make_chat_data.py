#!/usr/bin/env python3
"""Create exact-length chat datasets; optional shared token prefix. No API calls."""
import argparse
import hashlib
import json
import math
import random
from pathlib import Path

WORDS = ('river mountain forest science planet network memory language crystal valley '
         'winter summer autumn spring energy signal matrix ocean village bridge garden '
         'yellow purple silver copper vector number chapter theory method result system '
         'travel paper window architecture learning experiment').split()


def longest_prefix(first, second):
    length = 0
    for a, b in zip(first, second):
        if a != b:
            break
        length += 1
    return length


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--count', type=int, default=32)
    parser.add_argument('--input-tokens', type=int, required=True)
    parser.add_argument('--output-tokens', type=int, default=1024)
    parser.add_argument('--prefix-ratio', type=float, default=0)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--chat-template-kwargs', type=json.loads, default={})
    parser.add_argument('--trust-remote-code', action='store_true')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.count < 2 or min(args.input_tokens, args.output_tokens) < 1:
        parser.error('count must be >=2 and token lengths positive')
    if not 0 <= args.prefix_ratio < 1:
        parser.error('prefix-ratio must be in [0,1)')
    if args.out_dir.exists():
        parser.error('Choose a new out-dir; existing data is never overwritten')

    if not isinstance(args.chat_template_kwargs, dict):
        parser.error('chat-template-kwargs must be a JSON object')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        args.model, trust_remote_code=args.trust_remote_code)
    def encode(text):
        return tokenizer.encode(text, add_special_tokens=False)
    def chat_ids(text):
        prompt = tokenizer.apply_chat_template(
            [{'role': 'user', 'content': text}], tokenize=False,
            add_generation_prompt=True, **args.chat_template_kwargs)
        return encode(prompt)
    def join(shared, tail):
        return shared + ' ' + tail if shared else tail

    overhead = len(chat_ids(''))
    if args.input_tokens <= overhead + 32:
        parser.error('Input budget is too short for this chat template')
    target_prefix = math.floor(args.input_tokens * args.prefix_ratio)
    shared = ''
    if target_prefix:
        if target_prefix <= overhead + 16:
            parser.error('Requested prefix is too short for this chat template')
        rng = random.Random(args.seed - 1)
        raw = ' '.join(rng.choices(WORDS, k=target_prefix * 2))
        shared = tokenizer.decode(encode(raw)[:target_prefix - overhead])
        for _ in range(32):
            a = chat_ids(join(shared, WORDS[0] + ' calibration tail'))
            b = chat_ids(join(shared, WORDS[1] + ' calibration tail'))
            actual = longest_prefix(a, b)
            difference = target_prefix - actual
            if difference == 0:
                break
            if difference > 0:
                shared += ' a' * difference
            else:
                ids = encode(shared)
                shared = tokenizer.decode(ids[:len(ids) + difference])
        else:
            raise RuntimeError('Could not calibrate an exact shared prefix')
        print(f'Calibrated common prefix: {actual} tokens', flush=True)

    def fit_tail(tail, target):
        remaining = target - len(chat_ids(shared))
        if remaining < 16:
            raise RuntimeError('Insufficient unique suffix budget')
        tail = tokenizer.decode(encode(tail)[:remaining + 8])
        for _ in range(64):
            content = join(shared, tail)
            ids = chat_ids(content)
            difference = target - len(ids)
            if difference == 0:
                return content, ids
            if difference > 0:
                tail += ' a' * difference
            else:
                tail_ids = encode(tail)
                keep = len(tail_ids) + difference
                if keep <= 0:
                    raise RuntimeError('Suffix exhausted during length fitting')
                tail = tokenizer.decode(tail_ids[:keep])
        raise RuntimeError('Could not fit exact chat input length')

    rows, checks, reference, common_length, hashes = [], [], None, None, set()
    for index in range(args.count):
        rng = random.Random(args.seed + index)
        tail = WORDS[index % len(WORDS)] + ' ' + ' '.join(
            rng.choices(WORDS, k=max(128, (args.input_tokens - target_prefix) * 2)))
        content, ids = fit_tail(tail, args.input_tokens)
        digest = hashlib.sha256(content.encode()).hexdigest()
        assert digest not in hashes, 'Duplicate prompt'
        hashes.add(digest)
        if reference is None:
            reference, common_length = ids, len(ids)
        else:
            common_length = min(common_length, longest_prefix(reference, ids))
        if target_prefix:
            assert ids[:target_prefix] == reference[:target_prefix], 'Prefix differs'
        rows.append({'question': content, 'answer': '', 'max_out_len': args.output_tokens})
        checks.append({'id': index, 'chat_input_tokens': len(ids),
                       'content_tokens': len(encode(content)), 'sha256': digest})
        print(f'[{index + 1}/{args.count}] input={len(ids)}', flush=True)
    if target_prefix:
        assert common_length == target_prefix, (common_length, target_prefix)

    warmup_rows, warmup_checks = [], []
    if target_prefix:
        # These short suffixes differ from the measured requests, avoiding
        # full-prompt warm hits for any of the 32 measured samples.
        for index in range(8):
            content = join(shared, f'warmup calibration sentinel {index}')
            ids = chat_ids(content)
            assert ids[:target_prefix] == reference[:target_prefix]
            assert hashlib.sha256(content.encode()).hexdigest() not in hashes
            warmup_rows.append({'question': content, 'answer': '', 'max_out_len': 1})
            warmup_checks.append({'id': index, 'chat_input_tokens': len(ids),
                                  'shared_prefix_tokens': target_prefix})

    manifest = {
        'model': args.model, 'seed': args.seed, 'count': args.count,
        'input_tokens_each': args.input_tokens, 'target_output_tokens': args.output_tokens,
        'template_overhead_empty_chat': overhead,
        'chat_template_kwargs': args.chat_template_kwargs,
        'chat_template_sha256': hashlib.sha256(str(tokenizer.chat_template).encode()).hexdigest(),
        'requested_shared_prefix_ratio': args.prefix_ratio,
        'target_shared_prefix_tokens': target_prefix,
        'actual_common_prefix_tokens': common_length,
        'actual_common_prefix_ratio': common_length / args.input_tokens,
        'actual_cache_hit_ratio': 'Not measured; requires warmup and server metric deltas',
        'samples': checks, 'warmup_samples': warmup_checks,
    }
    args.out_dir.mkdir(parents=True)
    for name, data in [('data.jsonl', rows), ('warmup.jsonl', warmup_rows)]:
        if not data:
            continue
        with (args.out_dir / name).open('x', encoding='utf-8') as file:
            for row in data:
                file.write(json.dumps(row, ensure_ascii=False) + '\n')
    # Independently reread persisted rows, rather than trusting fitting-loop counts.
    saved = [json.loads(line) for line in
             (args.out_dir / 'data.jsonl').read_text(encoding='utf-8').splitlines()]
    saved_reference, saved_prefix, saved_hashes = None, None, set()
    for row, check in zip(saved, checks):
        ids = chat_ids(row['question'])
        digest = hashlib.sha256(row['question'].encode()).hexdigest()
        if len(ids) != args.input_tokens or digest != check['sha256'] or digest in saved_hashes:
            raise RuntimeError('Persisted dataset verification failed')
        saved_hashes.add(digest)
        if saved_reference is None:
            saved_reference, saved_prefix = ids, len(ids)
        else:
            saved_prefix = min(saved_prefix, longest_prefix(saved_reference, ids))
    if len(saved) != args.count or saved_prefix != common_length:
        raise RuntimeError('Persisted dataset count/prefix differs')
    if warmup_rows:
        saved_warmups = [json.loads(line) for line in
                         (args.out_dir / 'warmup.jsonl').read_text(encoding='utf-8').splitlines()]
        for row in saved_warmups:
            if chat_ids(row['question'])[:target_prefix] != saved_reference[:target_prefix]:
                raise RuntimeError('Persisted warmup prefix differs')
    manifest['verification'] = 'Saved JSONL reread, tokenized and checked'
    (args.out_dir / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items()
                      if k not in ('samples', 'warmup_samples')}, ensure_ascii=False), flush=True)
    print(f'Created {args.out_dir}; no API requests sent.', flush=True)


if __name__ == '__main__':
    main()
