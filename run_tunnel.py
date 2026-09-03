"""Cloudflare Secure Tunnel Launcher for ChatGPT Remote Access."""

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

URL_FILE = os.path.join(os.path.dirname(__file__), ".tunnel_url.txt")
LOCAL_TARGET = "http://127.0.0.1:8000"


def get_cloudflared_binary() -> str:
    which_path = shutil.which("cloudflared")
    if which_path:
        return which_path

    bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
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

    print(f"cloudflared binary not found locally. Downloading official release for {system}...")
    try:
        urllib.request.urlretrieve(url, local_bin)
        if os.name != "nt":
            os.chmod(local_bin, os.stat(local_bin).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print("Download complete.")
        return local_bin
    except Exception as e:
        print(f"Error downloading cloudflared automatically: {e}")
        print("Install manually from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        sys.exit(1)


def main():
    bin_path = get_cloudflared_binary()
    print(f"Starting Cloudflare Quick Tunnel to {LOCAL_TARGET}...")
    cmd = [bin_path, "tunnel", "--url", LOCAL_TARGET, "--no-autoupdate"]

    # Start process and stream stderr (cloudflared logs to stderr)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    tunnel_url = None
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    # Read output until URL is found
    for line in proc.stderr:
        print(line, end="", flush=True)
        match = pattern.search(line)
        if match:
            tunnel_url = match.group(0)
            break

    if not tunnel_url:
        print("Failed to detect tunnel URL from cloudflared output.")
        proc.terminate()
        sys.exit(1)

    with open(URL_FILE, "w") as f:
        f.write(tunnel_url.strip())

    print("\n" + "=" * 65)
    print("SECURE TUNNEL ESTABLISHED SUCCESSFULLY")
    print("=" * 65)
    print(f"Public Tunnel URL:          {tunnel_url}")
    print(f"ChatGPT OpenAPI Action:     {tunnel_url}/api/v1/chatgpt/openapi.json")
    print(f"ChatGPT Remote MCP SSE:     {tunnel_url}/mcp/sse")
    print(f"ChatGPT Remote MCP Message: {tunnel_url}/mcp/messages")
    print("=" * 65 + "\n")

    # Keep running
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
