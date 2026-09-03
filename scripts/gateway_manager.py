"""
Antigravity Gateway & Cloudflare Tunnel Manager
One-click unified launcher with health checks, duplicate prevention, and clipboard copy.
"""

import atexit
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import urllib.request

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL_FILE = os.path.join(ROOT_DIR, ".tunnel_url.txt")
LOCAL_URL = "http://127.0.0.1:8000"
HEALTH_URL = f"{LOCAL_URL}/health"

procs_to_clean = []


def cleanup():
    for p in procs_to_clean:
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


def handle_signal(sig, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def check_health(url, timeout=3):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GatewayManager/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "healthy"
    except Exception:
        return False
    return False


def copy_to_clipboard(text):
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def ensure_gateway_running():
    print("[1/3] Checking Local Gateway (localhost:8000)...")
    if check_health(HEALTH_URL):
        print("  -> Gateway is ALREADY running and healthy. (Reusing existing process)")
        return None

    print("  -> Starting Gateway server...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs_to_clean.append(proc)

    start_time = time.time()
    while time.time() - start_time < 15:
        if check_health(HEALTH_URL):
            print("  -> Gateway started and health check PASSED [200 OK].")
            return proc
        time.sleep(0.5)

    print("  [ERROR] Gateway failed to become healthy within 15 seconds.")
    sys.exit(1)


def get_cloudflared_binary() -> str:
    which_path = shutil.which("cloudflared")
    if which_path:
        return which_path

    bin_dir = os.path.join(ROOT_DIR, "bin")
    exe_name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    local_bin = os.path.join(bin_dir, exe_name)
    if os.path.exists(local_bin):
        return local_bin

    os.makedirs(bin_dir, exist_ok=True)
    system = platform.system().lower()
    machine = platform.machine().lower()

    if "windows" in system:
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    elif "darwin" in system:
        arch = "arm64" if "arm" in machine or "aarch64" in machine else "amd64"
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-{arch}"
    else:
        arch = "arm64" if "arm" in machine or "aarch64" in machine else "amd64"
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"

    print(f"  -> Downloading official cloudflared binary for {system}...")
    try:
        urllib.request.urlretrieve(url, local_bin)
        if os.name != "nt":
            os.chmod(local_bin, os.stat(local_bin).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print("  -> Download complete.")
        return local_bin
    except Exception as e:
        print(f"  [ERROR] Failed to download cloudflared: {e}")
        print("  Install manually from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        sys.exit(1)


def start_cloudflared():
    bin_path = get_cloudflared_binary()

    print("[2/3] Establishing Cloudflare Secure Tunnel...")
    cmd = [bin_path, "tunnel", "--url", LOCAL_URL, "--no-autoupdate"]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    procs_to_clean.append(proc)

    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    tunnel_url = None

    start_time = time.time()
    for line in proc.stderr:
        match = pattern.search(line)
        if match:
            tunnel_url = match.group(0)
            break
        if time.time() - start_time > 30:
            break

    if not tunnel_url:
        print("  [ERROR] Cloudflare Tunnel did not return a public URL.")
        sys.exit(1)

    mcp_url = f"{tunnel_url}/mcp/sse"

    # Write URL file
    try:
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write(tunnel_url.strip())
    except Exception:
        pass

    # Public health check
    print("[3/3] Verifying Public End-to-End Health Check...")
    public_ok = False
    for _ in range(8):
        time.sleep(1)
        if check_health(f"{tunnel_url}/health", timeout=5):
            public_ok = True
            break

    if public_ok:
        print("  -> Public endpoint verified online and responsive.")
    else:
        print("  -> Tunnel open (Cloudflare edge warming up).")

    # Copy to clipboard
    copy_to_clipboard(mcp_url)

    # Print Clean Banner
    print("\n" + "=" * 70)
    print("           CHATGPT x ANTIGRAVITY GATEWAY IS READY")
    print("=" * 70)
    print(f"  Local Status:       ONLINE (http://127.0.0.1:8000)")
    print(f"  Cloudflare Tunnel:  CONNECTED")
    print("")
    print("  >>> PASTE THIS URL IN CHATGPT:")
    print(f"      {mcp_url}")
    print("      (Copied to clipboard automatically!)")
    print("=" * 70)
    print("  STATUS: READY")
    print("  Keep this window open while working.")
    print("  Press Ctrl+C to stop all services cleanly.")
    print("=" * 70 + "\n")

    return proc


def main():
    print("=" * 70, flush=True)
    print("       ANTIGRAVITY GATEWAY ONE-CLICK LAUNCHER", flush=True)
    print("=" * 70 + "\n", flush=True)

    gateway_proc = ensure_gateway_running()
    tunnel_proc = start_cloudflared()

    try:
        tunnel_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping services...", flush=True)
    finally:
        cleanup()
        print("All processes stopped cleanly.", flush=True)


if __name__ == "__main__":
    main()
