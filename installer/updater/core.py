"""Serenus signed, side-by-side update primitives. No execution of manifest commands."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

MAX_ARCHIVE = 150 * 1024 * 1024
MAX_UNCOMPRESSED = 400 * 1024 * 1024
MAX_FILES = 4000
VERSION = re.compile(r'^\d+\.\d+\.\d+(?:-(?:rc|beta)\.\d+)?$')

class UpdateError(RuntimeError):
    pass

def canonical(m):
    return json.dumps(m, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

def check_manifest(m, *, platform='windows-amd64'):
    if not isinstance(m, dict) or m.get('schema') != 1 or not VERSION.fullmatch(str(m.get('version', ''))):
        raise UpdateError('Manifest o versione non validi')
    v=m['version']
    if m.get('platform') != platform or m.get('channel') not in ('stable', 'beta'):
        raise UpdateError('Piattaforma o canale non compatibili')
    if m['channel']=='stable' and '-' in v:
        raise UpdateError('Versione preliminare nel canale stabile')
    if m.get('asset') != f'serenus-app-{v}.zip':
        raise UpdateError('Nome pacchetto non valido')
    h=m.get('sha256','')
    if not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h):
        raise UpdateError('Hash SHA-256 non valido')
    if not isinstance(m.get('size_bytes'),int) or not (0 < m['size_bytes'] <= MAX_ARCHIVE):
        raise UpdateError('Dimensioni pacchetto non valide')
    if m.get('data_schema_version') != 1:
        raise UpdateError('Schema dati non supportato: aggiornamento bloccato')
    return m

def verify_manifest(manifest_bytes, signature_bytes, public_key_bytes):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        m=json.loads(manifest_bytes)
        check_manifest(m)
        # No ambiguity in signed representation; checks only canonical JSON.
        if manifest_bytes != canonical(m):
            raise UpdateError('Manifest non canonico')
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_bytes.strip(),validate=True))
        key.verify(base64.b64decode(signature_bytes.strip(),validate=True), manifest_bytes)
        return m
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError('Firma del rilascio non valida') from exc

def verify_archive(path, m):
    path=Path(path)
    if path.stat().st_size != m['size_bytes'] or path.stat().st_size > MAX_ARCHIVE:
        raise UpdateError('Dimensione ZIP differente dal manifest')
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    if h.hexdigest() != m['sha256']:
        raise UpdateError('SHA-256 ZIP non corrispondente')

def safe_extract(path, dest):
    dest=Path(dest)
    dest.mkdir(parents=True,exist_ok=False)
    try:
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if len(infos)>MAX_FILES or sum(i.file_size for i in infos)>MAX_UNCOMPRESSED:
                raise UpdateError('ZIP troppo grande')
            seen=set()
            for entry in infos:
                name=entry.filename.replace('\\','/')
                p=PurePosixPath(name)
                if (not name or name.startswith('/') or '\x00' in name or ':' in name or
                    any(x in ('','..') for x in p.parts) or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                    raise UpdateError('Percorso non sicuro nello ZIP')
                relative=str(p).casefold()
                if relative in seen: raise UpdateError('File duplicato nello ZIP')
                seen.add(relative)
                target=dest.joinpath(*p.parts)
                if entry.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(entry) as src, target.open('xb') as out:
                    shutil.copyfileobj(src,out)
        if not (dest/'app'/'app.py').is_file() or not (dest/'app'/'requirements.txt').is_file():
            raise UpdateError('Pacchetto incompleto: app/app.py o requirements.txt mancante')
    except Exception:
        shutil.rmtree(dest,ignore_errors=True)
        raise

def atomic_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.state-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,indent=2); f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def load_state(root):
    p=Path(root)/'state'/'update-state.json'
    if not p.exists():return {'current':'legacy','previous':None}
    try:
        data=json.loads(p.read_text('utf-8'))
        if not isinstance(data,dict):raise ValueError()
        return data
    except (ValueError,OSError):
        raise UpdateError('Stato aggiornamenti danneggiato; nessuna modifica effettuata')

def set_active(root, version):
    root=Path(root); state=load_state(root)
    if version != 'legacy':
        if not VERSION.fullmatch(version) or not (root/'versions'/version/'app'/'app.py').exists() or not (root/'versions'/version/'.venv'/'Scripts'/'python.exe').exists():
            raise UpdateError('Versione non installata completamente')
    if version==state.get('current'):return state
    atomic_json(root/'state'/'update-state.json',{'current':version,'previous':state.get('current')})
    return load_state(root)

def rollback(root):
    state=load_state(root)
    previous=state.get('previous')
    if not previous:raise UpdateError('Nessuna versione precedente da ripristinare')
    return set_active(root,previous)
