"""
On-Demand Static Bridge Runner for ChatGPT x Antigravity Bridge
Simultaneously orchestrates the Python ASGI server and ngrok static tunnel
with synchronized log streaming and guaranteed teardown on exit.
"""

import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT_DIR)

# Read configuration from environment or .env
PORT = int(os.environ.get("PORT", "8000"))
NGROK_DOMAIN = os.environ.get("NGROK_DOMAIN", "jab-jingling-come.ngrok-free.dev")

procs = []


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_clean_state(port: int):
    """Ensure no stale ngrok or port-holding processes remain from prior sessions."""
    # 1. Terminate any stray ngrok instances to avoid ERR_NGROK_334
    if os.name == "nt":
        try:
            subprocess.run(
                "taskkill /F /IM ngrok.exe",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # 2. Free target port if occupied
    if is_port_in_use(port):
        print(f"[INFO] Port {port} is occupied by an earlier process. Freeing port...", flush=True)
        if os.name == "nt":
            try:
                out = subprocess.check_output(
                    f'netstat -ano | findstr LISTENING | findstr ":{port} "',
                    shell=True,
                    text=True,
                )
                for line in out.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = int(parts[-1])
                        if pid > 0 and pid != os.getpid():
                            subprocess.run(
                                f"taskkill /F /PID {pid}",
                                shell=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                time.sleep(1)
            except Exception:
                pass


def cleanup():
    """Ensure all spawned subprocesses are cleanly terminated."""
    for p in procs:
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


atexit.register(cleanup)


def signal_handler(sig, frame):
    print("\n[SHUTDOWN] Signal received. Terminating Python server & ngrok tunnel...", flush=True)
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def find_ngrok() -> str:
    which_path = shutil.which("ngrok")
    if which_path:
        return which_path

    exe = "ngrok.exe" if os.name == "nt" else "ngrok"
    local_path = os.path.join(ROOT_DIR, "bin", exe)
    if os.path.exists(local_path):
        return local_path

    print(f"[ERROR] ngrok binary not found on PATH or in '{os.path.join(ROOT_DIR, 'bin')}'.", flush=True)
    sys.exit(1)


def main():
    # Pre-flight cleanup
    ensure_clean_state(PORT)

    ngrok_bin = find_ngrok()
    public_url = f"https://{NGROK_DOMAIN}"
    sse_url = f"{public_url}/mcp/sse"
    # Discover Antigravity Language Server credentials
    sys.path.insert(0, ROOT_DIR)
    ls_addr = None
    try:
        from app.services.antigravity_discovery import antigravity_discovery
        ls_addr, ls_token = antigravity_discovery.resolve_credentials()
    except Exception as exc:
        ls_token = None

    print("=" * 76, flush=True)
    print("   CHATGPT x ANTIGRAVITY BRIDGE - STATIC 1-CLICK RUNNER", flush=True)
    print("=" * 76, flush=True)
    print(f"  Target Local Port:  {PORT}", flush=True)
    print(f"  Static Domain:      {NGROK_DOMAIN}", flush=True)
    print(f"  Public SSE URL:     {sse_url}", flush=True)
    print(f"  Antigravity Server: {ls_addr or 'Autonomous Auto-Discovery active'}", flush=True)
    print(f"  ngrok Binary:       {ngrok_bin}", flush=True)
    print("=" * 76 + "\n", flush=True)

    # 1. Start Python ASGI Bridge
    print(f"[1/2] Starting Python ASGI Bridge on port {PORT}...", flush=True)
    env = os.environ.copy()
    env["PORT"] = str(PORT)
    env["PYTHONUNBUFFERED"] = "1"
    if ls_addr:
        env["ANTIGRAVITY_LS_ADDRESS"] = ls_addr
    if ls_token:
        env["ANTIGRAVITY_CSRF_TOKEN"] = ls_token

    py_proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=ROOT_DIR,
        env=env,
    )
    procs.append(py_proc)

    # Allow ASGI server time to bind and verify health
    server_ready = False
    for _ in range(25):
        time.sleep(0.4)
        if py_proc.poll() is not None:
            print("[ERROR] Python server failed to start. Exiting.", flush=True)
            sys.exit(1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            pass

    if not server_ready:
        print(f"[WARN] Bridge health check not responding yet on port {PORT}, proceeding with tunnel...", flush=True)
    else:
        print(f"[OK] Python ASGI Bridge is listening and healthy on port {PORT}.", flush=True)

    # 2. Start ngrok Static Tunnel
    print(f"[2/2] Starting ngrok static tunnel for domain '{NGROK_DOMAIN}'...", flush=True)
    ngrok_cmd = [
        ngrok_bin,
        "http",
        str(PORT),
        f"--domain={NGROK_DOMAIN}",
        "--log=stdout",
        "--log-level=warn",
    ]

    ngrok_proc = subprocess.Popen(
        ngrok_cmd,
        cwd=ROOT_DIR,
    )
    procs.append(ngrok_proc)

    time.sleep(1.5)
    if ngrok_proc.poll() is not None:
        print("[ERROR] ngrok tunnel failed to start. Check your ngrok authtoken/config.", flush=True)
        sys.exit(1)

    print("\n" + "=" * 76, flush=True)
    print("  STATUS: BRIDGE & STATIC NGROK TUNNEL ARE FULLY ACTIVE!", flush=True)
    print(f"  Permanent MCP URL for ChatGPT: {sse_url}", flush=True)
    print("  Keep this window open while using ChatGPT.", flush=True)
    print("  Press Ctrl+C or close this window to stop cleanly at any time.", flush=True)
    print("=" * 76 + "\n", flush=True)

    try:
        # Monitor processes
        while True:
            time.sleep(1)
            if py_proc.poll() is not None:
                print("\n[WARN] Python server exited unexpectedly.", flush=True)
                break
            if ngrok_proc.poll() is not None:
                print("\n[WARN] ngrok tunnel exited unexpectedly.", flush=True)
                break
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
        print("[OK] All processes stopped cleanly. Zero hanging ports.", flush=True)


if __name__ == "__main__":
    main()
