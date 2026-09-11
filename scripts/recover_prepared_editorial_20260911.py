#!/usr/bin/env python3
"""Recover the known prepared tree without weakening content checks.

The candidate is assembled in a temporary copy. Canonical files are updated
only after all validations pass. Failed candidates remain clearly labelled
recovery inputs; no manuscript count or approval is inflated.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'Matsu71/Psychology_Blog'
BASE = 'd114288fd1f106c01fd4f9bf3f4c5119305a603f'
PREPARED = 'a453fc1d3883ed0151b3f8960cab5cb61a9789c5'
REPORT = 'data/research/recovery_prepared_editorial_20260911.json'
ALLOWED = ('articles/', 'data/', 'docs/', 'research/', 'scripts/', 'schemas/')


def api(path: str) -> dict:
    url = 'https://api.github.com/repos/' + REPO + path
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'PsychologyEditorialRecovery/1.0'}
    token = os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def tree(sha: str) -> dict:
    value = api('/git/trees/' + sha + '?recursive=1')
    if value.get('truncated'):
        raise ValueError('Tree listing was truncated; refusing partial recovery.')
    return {item['path']: item for item in value['tree'] if item['type'] == 'blob'}


def git(*args: str, cwd: Path = ROOT) -> bytes:
    return subprocess.check_output(['git', *args], cwd=cwd)


def allowed(path: str) -> bool:
    return (path == 'README.md' or path.startswith(ALLOWED)) and '..' not in Path(path).parts


def write_json(root: Path, path: str, value: dict) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    starting_commit = git('rev-parse', 'HEAD').decode().strip()
    base, prepared = tree(BASE), tree(PREPARED)
    changes = {p: entry for p, entry in prepared.items()
               if allowed(p) and entry['sha'] != base.get(p, {}).get('sha')}
    if not changes:
        raise ValueError('No recoverable prepared changes were found.')
    conflicts = []
    for path, entry in changes.items():
        local = ROOT / path
        current = git('hash-object', str(local)).decode().strip() if local.is_file() else None
        if current not in (base.get(path, {}).get('sha'), entry['sha']):
            conflicts.append(path)
    if conflicts:
        raise ValueError('Concurrent content needs reconciliation: ' + ', '.join(conflicts))
    report = {'schema_version': '1.0', 'starting_commit': starting_commit,
              'base_tree': BASE, 'prepared_tree': PREPARED,
              'candidate_paths': list(changes), 'canonical_integrated': False,
              'publication_approval_granted': False, 'goal_completed': False,
              'validation': [], 'errors': []}
    with tempfile.TemporaryDirectory(prefix='psychology-checked-') as directory:
        work = Path(directory)
        archive = git('archive', '--format=tar', 'HEAD')
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                if member.name.startswith('/') or '..' in Path(member.name).parts or member.issym() or member.islnk():
                    raise ValueError('Unsafe archived entry: ' + member.name)
            tar.extractall(work)
        for path, entry in changes.items():
            blob = api('/git/blobs/' + entry['sha'])
            if blob.get('encoding') != 'base64':
                raise ValueError('Unexpected blob encoding: ' + path)
            payload = base64.b64decode(blob['content'])
            payload.decode('utf-8')
            check = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
            if check != entry['sha']:
                raise ValueError('Blob hash mismatch: ' + path)
            target = work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        # Give validators a local baseline; no credentials enter the candidate copy.
        subprocess.run(['git', 'init', '-q'], cwd=work, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Validation baseline'], cwd=work, check=True)
        subprocess.run(['git', 'config', 'user.email', 'validation@localhost.invalid'], cwd=work, check=True)
        subprocess.run(['git', 'add', '.'], cwd=work, check=True)
        subprocess.run(['git', 'commit', '-qm', 'Isolated validation baseline'], cwd=work, check=True)
        commands = [
            ['python3', 'scripts/apply_reviewed_delivery.py'],
            ['python3', 'scripts/reconcile_article_progress.py'],
            ['python3', 'scripts/validate.py'],
            ['python3', 'scripts/validate_research.py'],
            ['python3', 'scripts/validate_round3.py'],
            ['python3', 'scripts/validate_editorial_pass.py'],
            ['python3', 'scripts/validate_reviewed_delivery.py'],
            ['python3', 'scripts/reconcile_article_progress.py', '--check'],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=work, text=True, capture_output=True, timeout=120)
            report['validation'].append({'command': command, 'returncode': result.returncode,
                                          'stdout': result.stdout[-20000:], 'stderr': result.stderr[-20000:]})
            if result.returncode:
                report['errors'].append('Validation failed; canonical content was not replaced.')
                break
        else:
            before = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for prefix in ('articles', 'data', 'docs') for p in (work / prefix).rglob('*') if p.is_file()}
            repeat = subprocess.run(commands[0], cwd=work, text=True, capture_output=True, timeout=120)
            subprocess.run(commands[1], cwd=work, check=True, capture_output=True, timeout=120)
            after = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for prefix in ('articles', 'data', 'docs') for p in (work / prefix).rglob('*') if p.is_file()}
            if repeat.returncode or before != after:
                report['errors'].append('Regeneration is not stable; canonical replacement remains blocked.')
            else:
                for path in work.rglob('*'):
                    relative = str(path.relative_to(work))
                    if path.is_file() and allowed(relative):
                        target = ROOT / relative
                        if not target.is_file() or target.read_bytes() != path.read_bytes():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(path, target)
                report['canonical_integrated'] = True
                report['article_progress'] = json.loads((work / 'data/articles/progress.json').read_text())
        if not report['canonical_integrated']:
            # Retain authored inputs on main, but never advertise them as validated manuscripts.
            archive_root = ROOT / 'research/recovery_archive/prepared-20260911'
            for path in changes:
                if path.startswith('research/') and path.endswith(('.json', '.md', '.psv')):
                    target = archive_root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(work / path, target)
            report['recovery_archive'] = str(archive_root.relative_to(ROOT))
    write_json(ROOT, REPORT, report)
    print(json.dumps({k: report[k] for k in ('canonical_integrated', 'errors', 'prepared_tree')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
