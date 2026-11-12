#!/usr/bin/env bash
# Server-side mirror download -> extracted images -> locally generated ZIP.
# Usage: PYTHON=/path/to/venv/bin/python bash download_hallusion_images.sh /path/to/HallusionBench
# Requires curl, sha256sum, and pyarrow/Pillow in the selected Python environment.
set -euo pipefail

REPO_DIR="${1:?Pass the directory containing official HallusionBench.json}"
PYTHON="${PYTHON:-python3}"
cd "$REPO_DIR"

curl -fL --retry 3 --connect-timeout 30 \
  -o HallusionBench.image.parquet.part \
  'https://huggingface.co/datasets/lmms-lab-encoder/HallusionBench/resolve/main/data/image-00000-of-00001.parquet'
echo 'fd46946fa6b3f15ab8c8e2e0dacf54bc801db7915f17a47cec5ca872f30de2a9  HallusionBench.image.parquet.part' | sha256sum -c -
mv HallusionBench.image.parquet.part HallusionBench.image.parquet

"$PYTHON" - <<'PY'
from pathlib import Path
import io
import json
import zipfile
import pyarrow.parquet as pq
from PIL import Image

questions = json.loads(Path('HallusionBench.json').read_text(encoding='utf-8'))
keys = ('category', 'subcategory', 'set_id', 'figure_id', 'question_id')
identity = lambda row: tuple(str(row[k]) for k in keys)
mirror = {}
for row in pq.read_table('HallusionBench.image.parquet').to_pylist():
    key = identity(row)
    if key in mirror:
        raise ValueError(f'Duplicate mirror question: {key}')
    mirror[key] = row
root = Path('hallusion_bench').resolve()
images = {}
visual_count = 0
for row in questions:
    if int(row['visual_input']) == 0:
        continue
    other = mirror[identity(row)]
    for field in ('question', 'gt_answer', 'gt_answer_details', 'visual_input'):
        if str(row[field]) != str(other[field]):
            raise ValueError(f'Question mismatch: {identity(row)}, {field}')
    name = Path(row['filename'])
    if name.parts[0] == 'hallusion_bench':
        name = Path(*name.parts[1:])
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f'Unsafe image path: {name}')
    blob = other['image']['bytes']
    with Image.open(io.BytesIO(blob)) as image:
        image.verify()
    if path in images and images[path] != blob:
        raise ValueError(f'Conflicting image: {name}')
    images[path] = blob
    visual_count += 1
if (len(questions), visual_count, len(images)) != (1129, 951, 346):
    raise ValueError('Question/image counts differ from this verified mirror version')
for path, blob in images.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != blob:
        raise ValueError(f'Existing image differs; refusing overwrite: {path}')
    if not path.exists():
        path.write_bytes(blob)
archive = Path('hallusion_bench.mirror.zip')
if not archive.exists():
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(images):
            z.write(path, 'hallusion_bench/' + path.relative_to(root).as_posix())
with zipfile.ZipFile(archive) as z:
    if z.testzip() is not None:
        raise ValueError('ZIP CRC failed')
    for path, blob in images.items():
        if z.read('hallusion_bench/' + path.relative_to(root).as_posix()) != blob:
            raise ValueError(f'Archive image differs: {path}')
print(f'Validated {visual_count} image questions, {len(images)} unique images')
print(archive.resolve())
PY
