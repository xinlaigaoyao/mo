#!/usr/bin/env python3
"""Read-only static audit of a Zenith Terminal ZIP or extracted root.

No uploaded module is imported or executed. Python files are parsed with ast.parse;
optional Node --check parses JavaScript without running it. Output is an independent
report, not a security certification or proof of game compatibility.
Requires Python 3.11+; Node.js is optional.
Usage: python audit_zenith.py "ZenithTerminal-0.3.0-alpha (1).zip" --out audit.json
"""
from __future__ import annotations
import argparse
import ast
import collections
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import zipfile

MAX_MEMBER = 32 * 1024 * 1024  # only text files below this size are read
MAX_TOTAL = 2 * 1024**3

class Reader:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.z = None
        if path.is_file():
            self.z = zipfile.ZipFile(path)
            info = self.z.infolist()
            names = [i.filename for i in info]
            if len(names) != len(set(names)):
                raise ValueError('Duplicate archive member names')
            if sum(i.file_size for i in info) > MAX_TOTAL:
                raise ValueError('Uncompressed archive exceeds 2 GiB limit')
            for i in info:
                p = PurePosixPath(i.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename:
                    raise ValueError(f'Unsafe archive member: {i.filename}')
                if stat.S_ISLNK(i.external_attr >> 16):
                    raise ValueError(f'Symlink archive member: {i.filename}')
            self.meta = {i.filename: i.file_size for i in info if not i.is_dir()}
        else:
            if not path.is_dir():
                raise ValueError('Input must be an existing ZIP or directory')
            self.meta = {str(p.relative_to(self.path)).replace(os.sep, '/'): p.stat().st_size
                         for p in self.path.rglob('*') if p.is_file() and not p.is_symlink()}
        roots = [p[:-len('Launcher/bbmod.py')] for p in self.meta if p.endswith('Launcher/bbmod.py')]
        if len(roots) != 1:
            raise ValueError(f'Expected one Launcher/bbmod.py, found {len(roots)}')
        self.root = roots[0]
        self.launcher = self.root + 'Launcher/'
    def read(self, name: str) -> bytes:
        if name not in self.meta:
            raise FileNotFoundError(name)
        if self.meta[name] > MAX_MEMBER:
            raise ValueError(f'Text member exceeds size cap: {name}')
        if self.z:
            return self.z.read(name)
        p = (self.path / name).resolve()
        if self.path not in p.parents:
            raise ValueError(f'Outside input root: {p}')
        return p.read_bytes()
    def text(self, name: str) -> str:
        return self.read(name).decode('utf-8-sig')
    def close(self):
        if self.z:
            self.z.close()

def walk_refs(obj, used: set[int]):
    if isinstance(obj, dict):
        if set(obj) == {'rid'} and isinstance(obj['rid'], int):
            used.add(obj['rid'])
        for value in obj.values(): walk_refs(value, used)
    elif isinstance(obj, list):
        for value in obj: walk_refs(value, used)

def audit(source: Path, check_js: bool = True) -> dict:
    r = Reader(source)
    out = {'scope': 'static only; no game build, install, execution or malware certification',
           'input': source.name, 'file_count': len(r.meta), 'uncompressed_bytes': sum(r.meta.values()),
           'package_root': r.root, 'errors': [], 'notes': [], 'mods': {}, 'logic_trees': [],
           'python_files_checked': 0, 'python_index': {}, 'json_files_checked': 0,
           'javascript_checked': 0, 'javascript_failures': [], 'source_hashes': {}}
    if source.is_file():
        with source.open('rb') as f: out['archive_sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
    out['script_path_checks'] = []
    json_objects = {}
    js = []
    for name in sorted(r.meta):
        if not name.startswith(r.root) or name.startswith(r.root + 'Interpreter/'):
            continue
        ext = PurePosixPath(name).suffix.lower()
        if ext not in {'.py', '.json', '.js', '.md', '.cs', '.bat'}: continue
        try:
            text = r.text(name)
            out['source_hashes'][name[len(r.root):]] = hashlib.sha256(r.read(name)).hexdigest()
            if ext == '.py':
                t = ast.parse(text, filename=name)
                out['python_files_checked'] += 1
                out['python_index'][name[len(r.root):]] = [
                    {'kind': type(n).__name__, 'name': n.name, 'start': n.lineno, 'end': n.end_lineno}
                    for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            elif ext == '.json':
                d = json.loads(text)
                json_objects[name] = d
                out['json_files_checked'] += 1
                if isinstance(d, dict) and isinstance(d.get('_actions'), list):
                    records = d.get('references', {}).get('RefIds', [])
                    ids = [rec.get('rid') for rec in records]
                    used = set()
                    walk_refs(d.get('_actions', []), used)
                    for rec in records: walk_refs(rec.get('data'), used)
                    missing = sorted(used - set(ids) - {-2})
                    action_names = [a.get('Name') for a in d['_actions']]
                    item = {'file': name[len(r.root):], 'actions': len(action_names), 'references': len(ids),
                            'duplicate_action_names': [k for k, v in collections.Counter(action_names).items() if v > 1],
                            'duplicate_rids': [k for k, v in collections.Counter(ids).items() if v > 1],
                            'unresolved_rids': missing,
                            'reference_classes': dict(collections.Counter(x.get('type', {}).get('class', '') for x in records))}
                    out['logic_trees'].append(item)
                    if missing: out['errors'].append({'file': name, 'unresolved_rids': missing})
            elif ext == '.js': js.append((name, text))
        except (UnicodeError, ValueError, SyntaxError, OSError) as e:
            out['errors'].append({'file': name, 'error': str(e)})
    for name, d in json_objects.items():
        if PurePosixPath(name).name not in ('mod.json', 'terminal.json') or not isinstance(d, dict): continue
        if not name.startswith(r.launcher): continue
        mid = d.get('id')
        if not mid: continue
        parent = str(PurePosixPath(name).parent) + '/'
        entry = out['mods'].setdefault(mid, {'descriptors': []})
        entry['descriptors'].append(name[len(r.root):])
        entry.update({k: d.get(k) for k in ('name', 'version', 'gameBuilds', 'dependencies')})
        if PurePosixPath(parent).name != mid:
            out['errors'].append({'file': name, 'error': 'Mod ID does not match folder'})
        content = d.get('content', {})
        if content:
            entry['content_sections'] = list(content)
            entry['table_edits'] = {k: len(v) for k, v in content.get('tables', {}).items()}
            entry['js_modules'] = [s['file'] for s in content.get('js', [])]
            entry['bundle_clones'] = len(content.get('bundleClones', []))
            entry['asset_patches'] = len(content.get('assets', []))
        paths = [(r.launcher + p, 'prepare') for p in d.get('prepare', [])]
        paths += [(parent + s['script'], 'importer') for s in content.get('importers', [])]
        paths += [(parent + s['appendFile'], 'appendFile') for s in content.get('js', []) if s.get('appendFile')]
        paths += [(parent + s['treeFile'], 'treeFile') for s in content.get('assets', []) if s.get('treeFile')]
        paths += [(parent + s, 'jsFiles') for s in content.get('jsFiles', {}).values()]
        for path, kind in paths:
            exists = path in r.meta
            out['script_path_checks'].append({'mod': mid, 'kind': kind, 'path': path[len(r.root):], 'exists': exists})
            if not exists: out['errors'].append({'mod': mid, 'kind': kind, 'missing': path})
        for i, spec in enumerate(content.get('js', [])):
            if spec.get('append'): js.append((name + f'#/content/js/{i}/append', spec['append']))
    for mid, info in out['mods'].items():
        for dep in info.get('dependencies') or []:
            if dep not in out['mods']: out['errors'].append({'mod': mid, 'missing_dependency': dep})
    node = shutil.which('node') if check_js else None
    if node:
        with tempfile.TemporaryDirectory(prefix='zenith-static-js-') as td:
            for i, (name, text) in enumerate(js):
                p = Path(td) / f'{i:03}.js'
                p.write_text(text, encoding='utf8')
                clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith('NODE_')}
                cp = subprocess.run([node, '--check', str(p)], capture_output=True, text=True, timeout=10, env=clean_env, cwd=td)
                out['javascript_checked'] += 1
                if cp.returncode:
                    out['javascript_failures'].append({'file': name, 'error': cp.stderr[:2000]})
    else:
        out['notes'].append('Node.js unavailable or disabled: JavaScript syntax checks skipped')
    out['notes'].append('Replacement fragments are not complete modules; anchor compatibility requires the actual game baseline.')
    out['notes'].append('Ruby terminal.json without mod.json is expected before prepare; generated Ruby trees are not present yet.')
    r.close()
    return out

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('--out', type=Path, default=Path('zenith_static_audit.json'))
    ap.add_argument('--no-node', action='store_true', help='Skip optional parser-only Node.js checks')
    a = ap.parse_args()
    try:
        result = audit(a.input, not a.no_node)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    except (ValueError, OSError, zipfile.BadZipFile, subprocess.TimeoutExpired) as e:
        ap.exit(2, f'Audit failed: {e}\n')
    print(json.dumps({k: result[k] for k in ['file_count','python_files_checked','json_files_checked','javascript_checked','errors','javascript_failures','logic_trees']}, ensure_ascii=False, indent=2))
    print('Report:', a.out)
    return 1 if result['errors'] or result['javascript_failures'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
