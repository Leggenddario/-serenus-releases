"""CI-only end-to-end check of the Windows Serenus_Setup.exe installation.

Uses only the Python bundled by the installer. Does NOT send API keys, create
projects, run a scientific calculation, or validate external AI services.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_installed(root: Path) -> tuple[Path, Path]:
    statefile = root / "state" / "update-state.json"
    ensure(statefile.is_file(), f"Missing updater state: {statefile}")
    data = json.loads(statefile.read_text(encoding="utf-8"))
    current = data.get("current")
    ensure(isinstance(current, str) and current != "legacy", f"Invalid active version: {current}")
    app = root / "versions" / current / "app"
    py = root / "versions" / current / ".venv" / "Scripts" / "python.exe"
    ensure(py.is_file(), f"Missing application Python: {py}")
    ensure((app / "app.py").is_file(), f"Missing app.py: {app}")
    ensure((app / "requirements.txt").is_file(), "Missing requirements.txt")
    for name in ("Apri_Serenus.bat", "Controlla_Aggiornamenti.bat", "Ripristina_Serenus.bat"):
        ensure((root / name).is_file(), f"Missing launcher: {name}")
    ensure((root / "launcher" / "release-public-key.txt").is_file(), "Missing public key")
    print(f"Installed version: {current}", flush=True)
    return py, app


def check_streamlit(py: Path, app: Path) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [str(py), "-m", "streamlit", "run", "app.py", "--server.headless=true",
               "--server.address=127.0.0.1", f"--server.port={port}",
               "--browser.gatherUsageStats=false"]
    print(f"Starting installed Streamlit on 127.0.0.1:{port}", flush=True)
    process = subprocess.Popen(command, cwd=app, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    try:
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"Streamlit exited {process.returncode}: {output[-3000:]}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as resp:
                    if resp.status == 200 and b"ok" in resp.read(64).lower():
                        print("PASS: Streamlit health endpoint returned OK", flush=True)
                        return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.5)
        raise AssertionError("Streamlit did not respond within 75 seconds")
    finally:
        process.terminate()
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=8)


def check_rollback_logic(root: Path) -> None:
    """Exercise state switch & rollback on disposable synthetic versions."""
    launcher = root / "launcher"
    sys.path.insert(0, str(launcher))
    from updater.core import set_active, load_state, rollback, UpdateError
    with tempfile.TemporaryDirectory(prefix="serenus-rollback-smoke-") as tmp:
        base = Path(tmp)
        for version in ("1.0.0", "1.0.1"):
            (base / "versions" / version / "app").mkdir(parents=True)
            (base / "versions" / version / "app" / "app.py").write_text("# test", encoding="utf-8")
            stub = base / "versions" / version / ".venv" / "Scripts" / "python.exe"
            stub.parent.mkdir(parents=True)
            stub.write_bytes(b"synthetic stub - never executed")
        set_active(base, "1.0.0")
        set_active(base, "1.0.1")
        ensure(load_state(base)["current"] == "1.0.1", "Activation failed")
        rollback(base)
        ensure(load_state(base)["current"] == "1.0.0", "Rollback failed")
        print("PASS: isolated update-state rollback", flush=True)


def main() -> int:
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Serenus"
    ensure(root.is_dir(), f"Installation directory not found: {root}")
    py, app = assert_installed(root)
    check_streamlit(py, app)
    check_rollback_logic(root)
    print("PASS: Installer smoke tests", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
