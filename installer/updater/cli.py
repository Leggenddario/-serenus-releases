"""External updater CLI; does not run inside Streamlit."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import urllib.error
from updater.core import (UpdateError,verify_manifest,verify_archive,safe_extract,
                          load_state,set_active,rollback,VERSION)

GITHUB_API='https://api.github.com'
MAX_META=128*1024

def fetch(url, *, max_bytes=MAX_META):
    u=urllib.parse.urlparse(url)
    if u.scheme!='https' or u.hostname not in ('api.github.com','github.com','release-assets.githubusercontent.com'):
        raise UpdateError('Dominio download non ammesso')
    req=urllib.request.Request(url,headers={'User-Agent':'Serenus-Updater/1.0','Accept':('application/vnd.github+json' if u.hostname=='api.github.com' else 'application/octet-stream')})
    with urllib.request.urlopen(req,timeout=20) as f:
        final=urllib.parse.urlparse(f.url)
        if final.scheme!='https' or final.hostname not in ('api.github.com','github.com','release-assets.githubusercontent.com'):
            raise UpdateError('Redirect non consentito')
        data=f.read(max_bytes+1)
    if len(data)>max_bytes:raise UpdateError('Risposta troppo grande')
    return data

def fetch_release(repo, channel):
    if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
        raise UpdateError('Nome repository non valido')
    if channel!='stable':raise UpdateError('Il canale beta non è ancora implementato')
    url=f'{GITHUB_API}/repos/{repo}/releases/latest'
    meta=json.loads(fetch(url))
    if meta.get('draft') or meta.get('prerelease'):raise UpdateError('Release non stabile')
    assets={a['name']:a for a in meta.get('assets',[])}
    for name in ('manifest.json','manifest.sig'):
        if name not in assets:raise UpdateError(f'Manca {name} nella release')
    def asset_url(name):
        url=assets[name]['browser_download_url']
        u=urllib.parse.urlparse(url)
        if u.scheme!='https' or u.hostname!='github.com' or not u.path.startswith('/'+repo+'/releases/download/'):
            raise UpdateError('Asset GitHub non valido')
        return url
    return asset_url,fetch(asset_url('manifest.json')),fetch(asset_url('manifest.sig'))

def install(root,manifest,zip_path, *, skip_health=False):
    """Prepare candidate using isolated venv; never modify active install before success."""
    root=Path(root); version=manifest['version']; versions=root/'versions';versions.mkdir(parents=True,exist_ok=True)
    target=versions/version
    if target.exists():raise UpdateError('La versione è già presente: non sovrascrivo')
    verify_archive(zip_path,manifest)
    stage=versions/f'.staging-{version}'
    if stage.exists():shutil.rmtree(stage)
    safe_extract(zip_path,stage)
    try:
        # A Windows venv must be built at its final path (relocation is unreliable).
        stage.rename(target)
        exe=target/'.venv'/'Scripts'/'python.exe'
        subprocess.run([sys.executable,'-m','venv',str(target/'.venv')],check=True,timeout=120)
        subprocess.run([str(exe),'-m','pip','install','-r',str(target/'app'/'requirements.txt')],check=True,timeout=900)
        # Lightweight static checks; full live health test is deferred to an actual Windows pilot.
        subprocess.run([str(exe),'-m','compileall','-q',str(target/'app')],check=True,timeout=120)
        if skip_health:
            raise UpdateError('Attivazione senza health check non autorizzata')
        health_check(exe,target/'app')
        set_active(root,version)
    except Exception:
        if stage.exists():shutil.rmtree(stage,ignore_errors=True)
        if target.exists():shutil.rmtree(target,ignore_errors=True)
        raise

def health_check(py,app):
    """Start Streamlit on an ephemeral localhost port and require healthy response."""
    import socket
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    cmd=[str(py),'-m','streamlit','run','app.py','--server.headless=true',
         f'--server.port={port}','--server.address=127.0.0.1','--browser.gatherUsageStats=false']
    p=subprocess.Popen(cmd,cwd=app,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if p.poll() is not None:break
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=2) as res:
                    if res.status==200 and b'ok' in res.read(100).lower():return
            except (OSError,urllib.error.URLError):pass
            time.sleep(.5)
        raise UpdateError('Test di avvio Streamlit fallito; versione attuale invariata')
    finally:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()

def cli(argv=None):
    a=argparse.ArgumentParser(description='Serenus Updater (fase pilota)')
    a.add_argument('action',choices=['status','check','apply','rollback'])
    a.add_argument('--root',type=Path,default=Path(os.getenv('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'Serenus')
    a.add_argument('--repo',default='')
    a.add_argument('--public-key',type=Path)
    a.add_argument('--channel',default='stable')
    args=a.parse_args(argv)
    try:
        if args.action=='status':print(json.dumps(load_state(args.root),indent=2));return 0
        if args.action=='rollback':print('Ripristino:',rollback(args.root));return 0
        if not args.repo or not args.public_key or not args.public_key.is_file():
            raise UpdateError('Repository GitHub e chiave pubblica non configurati: nessun download eseguito')
        url,raw,sig=fetch_release(args.repo,args.channel)
        m=verify_manifest(raw,sig,args.public_key.read_bytes())
        name=m['asset']
        if args.action=='check':print('Versione verificata:',m['version']);return 0
        current=load_state(args.root)['current']
        # No downgrade/sidegrade; use simple tuple for stable versions.
        if current!='legacy' and tuple(map(int,m['version'].split('-')[0].split('.'))) <= tuple(map(int,current.split('-')[0].split('.'))):
            raise UpdateError('Nessuna versione più recente')
        print('Download autenticato:',m['version'])
        archive=fetch(url(name),max_bytes=m['size_bytes'])
        temp=args.root/'downloads';temp.mkdir(parents=True,exist_ok=True)
        f=temp/name;f.write_bytes(archive)
        install(args.root,m,f)
        print('Aggiornamento completato. Riavvia Serenus.')
        return 0
    except (UpdateError,OSError,ValueError,subprocess.CalledProcessError) as e:
        print('ERRORE:',str(e),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(cli())
