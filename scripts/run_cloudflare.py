"""
Persistent Cloudflare HTTPS Tunnel daemon for 3D Printer Farm WebApp.
Binds to 127.0.0.1:8080 (or HTTP_PORT) and auto-reconnects on disconnection.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH, override=True)

HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
CLOUDFLARE_TUNNEL_TOKEN = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "").strip()


def update_env_webapp_url(new_url: str):
    """Updates WEBAPP_URL in .env file."""
    if not ENV_PATH.exists():
        return
    content = ENV_PATH.read_text(encoding="utf-8")
    clean_base = new_url.rstrip("/")
    full_webapp_url = f"{clean_base}/webapp"

    if "WEBAPP_URL=" in content:
        new_content = re.sub(r"WEBAPP_URL=.*", f"WEBAPP_URL={full_webapp_url}", content)
    else:
        new_content = content + f"\nWEBAPP_URL={full_webapp_url}\n"

    ENV_PATH.write_text(new_content, encoding="utf-8")
    print(f"✅ Updated .env WEBAPP_URL: {full_webapp_url}")


def run_daemon():
    print("🚀 Initializing Cloudflare HTTPS Tunnel Daemon...")

    while True:
        try:
            if CLOUDFLARE_TUNNEL_TOKEN:
                print("🌐 Connecting Cloudflare Named Tunnel using CLOUDFLARE_TUNNEL_TOKEN...")
                proc = subprocess.Popen(
                    ["cloudflared", "tunnel", "run", "--token", CLOUDFLARE_TUNNEL_TOKEN],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                )
                print("✨ Cloudflare Tunnel Daemon active with token.")
                proc.wait()
            else:
                print(f"🌐 Starting Cloudflare Quick Tunnel for http://127.0.0.1:{HTTP_PORT}...")
                try:
                    from pycloudflared import try_cloudflare

                    cluster = try_cloudflare(port=HTTP_PORT)
                    public_url = getattr(cluster, "tunnel", getattr(cluster, "url", ""))
                    print(f"✨ Cloudflare HTTPS Tunnel Active: {public_url}")
                    update_env_webapp_url(public_url)

                    # Monitor process lifetime
                    proc_obj = getattr(cluster, "process", None)
                    if proc_obj and hasattr(proc_obj, "wait"):
                        proc_obj.wait()
                except ImportError:
                    # Fallback to direct subprocess cloudflared invocation if pycloudflared unavailable
                    proc = subprocess.Popen(
                        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{HTTP_PORT}"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                    )
                    for line in proc.stdout:
                        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                        if match:
                            public_url = match.group(0)
                            print(f"✨ Cloudflare HTTPS Tunnel Active: {public_url}")
                            update_env_webapp_url(public_url)
                            break
                    proc.wait()

            print("⚠️ Cloudflare process exited. Reconnecting in 3 seconds...")
        except KeyboardInterrupt:
            print("🛑 Cloudflare Tunnel daemon stopped by user.")
            break
        except Exception as err:
            print(f"❌ Cloudflare connection error: {err}. Retrying in 5 seconds...")
        time.sleep(3)


if __name__ == "__main__":
    run_daemon()
