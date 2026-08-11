"""
Persistent Ngrok HTTPS Tunnel daemon for 3D Printer Farm WebApp.
Binds to 127.0.0.1:8080 and auto-reconnects on heartbeat timeouts.
"""
import os
import re
import sys
import time
import urllib.request
import json
from pathlib import Path
from pyngrok import ngrok, exception

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")

def update_env_webapp_url(new_url: str):
    """Updates WEBAPP_URL in .env file."""
    if not ENV_PATH.exists():
        return
    content = ENV_PATH.read_text(encoding="utf-8")
    full_webapp_url = f"{new_url.rstrip('/')}/webapp"
    
    if "WEBAPP_URL=" in content:
        new_content = re.sub(r'WEBAPP_URL=.*', f'WEBAPP_URL={full_webapp_url}', content)
    else:
        new_content = content + f"\nWEBAPP_URL={full_webapp_url}\n"
    
    ENV_PATH.write_text(new_content, encoding="utf-8")
    print(f"✅ Updated .env WEBAPP_URL: {full_webapp_url}")

def get_active_ngrok_url():
    """Queries local ngrok REST API for active tunnel URL."""
    try:
        req = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels")
        data = json.loads(req.read().decode("utf-8"))
        tunnels = data.get("tunnels", [])
        for t in tunnels:
            if t.get("proto") == "https" or t.get("public_url", "").startswith("https"):
                return t.get("public_url")
            elif t.get("public_url"):
                return t.get("public_url")
    except Exception:
        pass
    return None

def run_daemon():
    print("🚀 Initializing Ngrok HTTPS Tunnel Daemon...")
    if AUTHTOKEN:
        ngrok.set_auth_token(AUTHTOKEN)

    while True:
        try:
            public_url = get_active_ngrok_url()
            if not public_url:
                print("🌐 Connecting Ngrok tunnel to http://127.0.0.1:8080...")
                try:
                    tunnel = ngrok.connect("127.0.0.1:8080", "http")
                    public_url = tunnel.public_url
                except exception.PyngrokNgrokHTTPError as e:
                    if "ERR_NGROK_334" in str(e):
                        time.sleep(2)
                        public_url = get_active_ngrok_url()
                    if not public_url:
                        raise e

            print(f"✨ Ngrok HTTPS Tunnel Active: {public_url}")
            update_env_webapp_url(public_url)

            # Monitor process connection
            ngrok_process = ngrok.get_ngrok_process()
            ngrok_process.proc.wait()
            print("⚠️ Ngrok process exited. Reconnecting in 3 seconds...")
        except Exception as err:
            print(f"❌ Ngrok connection error: {err}. Retrying in 5 seconds...")
            try:
                ngrok.kill()
            except Exception:
                pass
        time.sleep(3)

if __name__ == "__main__":
    run_daemon()
