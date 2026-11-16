"""Start installed version; legacy fallback is retained for first bootstrap."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
try:
    from updater.core import load_state,UpdateError
except ModuleNotFoundError:
    from core import load_state,UpdateError

def command(root):
    root=Path(root)
    active=load_state(root)['current']
    if active=='legacy':
        py=root/'.venv'/'Scripts'/'python.exe';app=root/'app'
    else:
        py=root/'versions'/active/'.venv'/'Scripts'/'python.exe'
        app=root/'versions'/active/'app'
    if not py.exists() or not (app/'app.py').exists():
        raise UpdateError('Installazione incompleta: esegui il programma di ripristino')
    return [str(py),'-m','streamlit','run','app.py'],app

def main():
    root=Path(os.getenv('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'Serenus'
    try:
        cmd,cwd=command(root)
        return subprocess.call(cmd,cwd=cwd)
    except UpdateError as e:
        print('ERRORE Serenus:',e,file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
