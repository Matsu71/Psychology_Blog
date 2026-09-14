#!/usr/bin/env python3
"""One-time, hash-checked UTF-8 source delivery. Refuse conflicts before writing."""
from pathlib import Path, PurePosixPath
import base64, hashlib, json, lzma, shutil
ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT / '.delivery'
def digest(data):
    return hashlib.sha256(data).hexdigest()
def safe(name):
    p = PurePosixPath(name)
    if not isinstance(name, str) or p.is_absolute() or '..' in p.parts or not p.parts or '\\' in name:
        raise ValueError('Invalid relative path: ' + str(name))
    path = ROOT.joinpath(*p.parts)
    if any(x.is_symlink() for x in [path, *path.parents] if x != ROOT.parent):
        raise ValueError('Symlink refused: ' + name)
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Path escapes repository')
    return path
manifest = json.loads((DELIVERY / 'manifest.json').read_text())
parts = []
for item in manifest['parts']:
    raw = safe(item['path']).read_bytes()
    if len(raw) > 16000 or digest(raw) != item['sha256']:
        raise ValueError('Delivery part checksum failed: ' + item['path'])
    parts.append(raw)
encoded = b''.join(parts)
if len(encoded) > 1000000:
    raise ValueError('Delivery too large')
xz = base64.b64decode(encoded, validate=True)
if digest(xz) != manifest['xz_sha256']:
    raise ValueError('Compressed bundle checksum failed')
decoder = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
raw = decoder.decompress(xz, max_length=5 * 1024 * 1024)
if not decoder.eof or decoder.unused_data or digest(raw) != manifest['json_sha256']:
    raise ValueError('Source bundle checksum/size failed')
pack = json.loads(raw)
allowed = set(manifest['allowed_paths'])
paths = list(pack['files']) + [p['path'] for p in pack['patches']]
if len(paths) != len(set(paths)) or set(paths) != allowed:
    raise ValueError('Unexpected or duplicate delivery paths')
plans = {}
for name, content in pack['files'].items():
    path = safe(name)
    data = content.encode('utf-8')
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Existing new-file conflict: ' + name)
    plans[path] = data
for item in pack['patches']:
    path = safe(item['path'])
    if path.exists() and digest(path.read_bytes()) == item['target_sha256']:
        continue
    if item['path'] != item['base_path'] and path.exists():
        raise ValueError('Existing edition conflict: ' + item['path'])
    original = safe(item['base_path']).read_bytes()
    if digest(original) != item['base_sha256']:
        raise ValueError('Original changed; reconcile before applying: ' + item['base_path'])
    lines = original.decode('utf-8').splitlines(True)
    previous_end = 0
    for start, end, replacement in item['operations']:
        if not (previous_end <= start <= end <= len(lines)) or not isinstance(replacement, str):
            raise ValueError('Invalid source patch')
        previous_end = end
    for start, end, replacement in reversed(item['operations']):
        lines[start:end] = [replacement]
    data = ''.join(lines).encode('utf-8')
    if digest(data) != item['target_sha256']:
        raise ValueError('Patched source checksum failed: ' + item['path'])
    plans[path] = data
# Every conflict and checksum is checked before the first repository source write.
for path, data in plans.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
shutil.rmtree(DELIVERY)
print(f'Installed {len(paths)} ordinary source files; removed one-time delivery bundle.')
