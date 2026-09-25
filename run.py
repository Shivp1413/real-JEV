#!/usr/bin/env python3
"""
real-JEV one-command launcher.

Run:  python run.py

It will (all automatically):
  1. create a local virtual environment (.venv) and install dependencies,
  2. make sure Ollama is installed and running (guiding you if it isn't),
  3. pull the default small model (qwen2.5:1.5b) if you don't have any model yet,
  4. start the web server and open http://127.0.0.1:8080 in your browser.

Flags:
  --no-browser        don't auto-open the browser
  --host / --port     override bind address (default 127.0.0.1:8080)
  --model TAG         default model to use / pull (default qwen2.5:1.5b)
  --no-pull           don't auto-download a model
  --skip-ollama       don't touch Ollama (use demo mode or a custom backend)
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
INSTALL_JSON = ROOT / "install.json"
# Runtime cache for the downloaded Ollama binary+libs. On Linux this lives under
# ~/.cache so it is never part of the project/repo. Re-created automatically.
RUNTIME_DIR = Path.home() / ".cache" / "real-jev" / "ollama"
DEFAULT_MODEL = "qwen2.5:1.5b"
IS_WIN = platform.system() == "Windows"


def load_sources() -> dict:
    try:
        return json.loads(INSTALL_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def venv_python() -> Path:
    return VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")


def c(txt, code):  # tiny color helper
    if IS_WIN or not sys.stdout.isatty():
        return txt
    return f"\033[{code}m{txt}\033[0m"


def info(m): print(c("• " + m, "36"))
def ok(m): print(c("✓ " + m, "32"))
def warn(m): print(c("! " + m, "33"))
def err(m): print(c("✗ " + m, "31"))


# --------------------------------------------------------------------------- #
def ensure_venv_and_deps():
    if not venv_python().exists():
        info("Creating virtual environment (.venv)…")
        venv.EnvBuilder(with_pip=True).create(VENV)
    py = str(venv_python())
    info("Installing/updating dependencies…")
    subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=False)
    r = subprocess.run([py, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")])
    if r.returncode != 0:
        err("Dependency install failed. See the pip output above.")
        sys.exit(1)
    ok("Dependencies ready.")


def in_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == venv_python().resolve()
    except Exception:
        return False


# --------------------------------------------------------------------------- #
def detect_ram_gb() -> float:
    """Best-effort total system RAM in GB, cross-platform, no extra deps."""
    try:
        if IS_WIN:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1e9
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()
            return int(out) / 1e9
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024 / 1e9
    except Exception:
        pass
    return 8.0  # safe assumption


def pick_default_model(sources: dict, requested: str) -> str:
    # Honour an explicit non-default --model
    if requested and requested != DEFAULT_MODEL:
        return requested
    tiers = sources.get("default_model_by_ram_gb") or []
    ram = detect_ram_gb()
    chosen = DEFAULT_MODEL
    for t in sorted(tiers, key=lambda x: x.get("min_ram_gb", 0)):
        if ram >= t.get("min_ram_gb", 0):
            chosen = t.get("model", chosen)
    info(f"Detected ~{ram:.1f} GB RAM → default model '{chosen}'.")
    return chosen


def _local_ollama_bin() -> Path:
    return RUNTIME_DIR / "bin" / ("ollama.exe" if IS_WIN else "ollama")


def _apply_local_ollama_env() -> None:
    """Put a locally-installed Ollama on PATH + LD_LIBRARY_PATH for this process."""
    binp = _local_ollama_bin()
    if binp.exists():
        os.environ["PATH"] = str(binp.parent) + os.pathsep + os.environ.get("PATH", "")
        libdir = RUNTIME_DIR / "lib" / "ollama"
        if libdir.exists():
            os.environ["LD_LIBRARY_PATH"] = str(libdir) + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None or _local_ollama_bin().exists()


def ollama_running() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    info(f"Downloading {url} …")
    if shutil.which("curl"):
        subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(dest), url], check=True)
    else:
        import urllib.request
        urllib.request.urlretrieve(url, dest)


def _install_ollama_linux(sources: dict) -> bool:
    """No-sudo install: download the release tarball (binary + libs) and extract it
    into RUNTIME_DIR. Falls back to the official installer script if available."""
    arch = "arm64" if platform.machine().lower() in ("aarch64", "arm64") else "amd64"
    url = (sources.get("ollama", {}).get("binaries", {}) or {}).get(f"linux-{arch}")
    if url:
        try:
            archive = RUNTIME_DIR.parent / f"ollama-linux-{arch}.tar.zst"
            _download(url, archive)
            info("Extracting Ollama (binary + native libraries)…")
            RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            import tarfile
            import zstandard as zstd  # provided via requirements.txt
            with open(archive, "rb") as f, zstd.ZstdDecompressor().stream_reader(f) as r:
                with tarfile.open(fileobj=r, mode="r|") as tar:
                    tar.extractall(RUNTIME_DIR)
            archive.unlink(missing_ok=True)
            _apply_local_ollama_env()
            return _local_ollama_bin().exists()
        except Exception as e:  # noqa: BLE001
            warn(f"Local binary install failed ({e}); trying the official installer…")
    # Fallback: official script (may require sudo/root)
    script = sources.get("ollama", {}).get("install_script", "https://ollama.com/install.sh")
    if shutil.which("curl"):
        try:
            p1 = subprocess.Popen(["curl", "-fsSL", script], stdout=subprocess.PIPE)
            subprocess.run(["sh"], stdin=p1.stdout, check=True)
            return shutil.which("ollama") is not None
        except Exception as e:  # noqa: BLE001
            warn(f"Installer script did not complete: {e}")
    return False


def _install_ollama_macos(sources: dict) -> bool:
    if shutil.which("brew"):
        try:
            info("Installing Ollama via Homebrew…")
            subprocess.run(["brew", "install", "ollama"], check=True)
            return shutil.which("ollama") is not None
        except Exception as e:  # noqa: BLE001
            warn(f"brew install failed: {e}")
    url = sources.get("ollama", {}).get("binaries", {}).get("darwin")
    warn("Could not auto-install on macOS.")
    if url:
        print(f"    Download & install Ollama from: {url}")
    return False


def try_install_ollama(sources: dict) -> bool:
    system = platform.system()
    info("Ollama not found — installing it automatically…")
    if system == "Linux":
        return _install_ollama_linux(sources)
    if system == "Darwin":
        return _install_ollama_macos(sources)
    # Windows
    if shutil.which("winget"):
        try:
            subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent",
                            "--accept-source-agreements", "--accept-package-agreements"], check=True)
            return shutil.which("ollama") is not None
        except Exception as e:  # noqa: BLE001
            warn(f"winget install failed: {e}")
    url = sources.get("ollama", {}).get("binaries", {}).get("windows-amd64")
    if url:
        print(f"    Download & run the Ollama installer: {url}")
    return False


def ensure_ollama(auto_pull: bool, model: str) -> None:
    sources = load_sources()
    _apply_local_ollama_env()
    if not ollama_installed():
        if not try_install_ollama(sources):
            warn("Ollama could not be installed automatically.")
            print("    Install it (2 min) from: https://ollama.com/download")
            print("    Then re-run:  python run.py")
            print("    (real-JEV will still start in DEMO mode so you can see the UI.)")
            return
    _apply_local_ollama_env()
    ok("Ollama is installed.")

    if not ollama_running():
        info("Starting `ollama serve` in the background…")
        try:
            kwargs = {}
            if IS_WIN:
                kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
            else:
                kwargs["stdout"] = subprocess.DEVNULL
                kwargs["stderr"] = subprocess.DEVNULL
            subprocess.Popen(["ollama", "serve"], **kwargs)
        except Exception as e:
            warn(f"Couldn't auto-start Ollama: {e}. Run `ollama serve` in another terminal.")
        for _ in range(20):
            if ollama_running():
                break
            time.sleep(0.5)
    if ollama_running():
        ok("Ollama server is up.")
    else:
        warn("Ollama server not reachable yet; the app will start in demo mode until it is.")
        return

    if not auto_pull:
        return
    # Pull default model if the user has no models at all.
    try:
        import json
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            tags = json.loads(r.read()).get("models", [])
    except Exception:
        tags = []
    if not tags:
        info(f"No models installed yet — pulling default model '{model}' (~1 GB, one time)…")
        subprocess.run(["ollama", "pull", model], check=False)
        ok("Default model ready.")
    else:
        ok(f"{len(tags)} model(s) already installed.")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="real-JEV launcher")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="8080")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--skip-ollama", action="store_true")
    args = ap.parse_args()

    print(c("\n  🧠  real-JEV — local typed-decision playground\n", "35"))

    # Step 1: venv + deps, then re-exec inside the venv.
    if not in_venv():
        ensure_venv_and_deps()
        info("Relaunching inside the virtual environment…")
        os.execv(str(venv_python()), [str(venv_python()), str(ROOT / "run.py"), *sys.argv[1:]])

    # Step 2: pick a model that fits this machine's RAM, then set up Ollama
    chosen_model = pick_default_model(load_sources(), args.model)
    os.environ["REALJEV_MODEL"] = chosen_model
    if not args.skip_ollama:
        ensure_ollama(auto_pull=not args.no_pull, model=chosen_model)
    else:
        info("Skipping Ollama setup (per --skip-ollama).")

    # Step 3: launch the server
    os.environ["REALJEV_MODEL"] = chosen_model
    url = f"http://{args.host}:{args.port}"
    print()
    ok(f"Starting real-JEV at  {c(url, '1;36')}")
    print(c("  Open that URL in your browser. Press Ctrl+C to stop.\n", "90"))

    if not args.no_browser:
        try:
            import threading
            import webbrowser
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        except Exception:
            pass

    import uvicorn
    uvicorn.run("app.server:app", host=args.host, port=int(args.port), log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
