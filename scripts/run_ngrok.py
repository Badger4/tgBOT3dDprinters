"""
Ngrok HTTPS Tunnel Runner Script for Telegram WebApp SPA.
Configures pyngrok auth token, opens an HTTPS tunnel to local HTTP_PORT,
and automatically updates WEBAPP_URL in .env.
"""

import sys
import time
from pathlib import Path

# Add project root directory to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import ENV_PATH, HTTP_PORT, NGROK_AUTHTOKEN, logger


def update_env_webapp_url(new_url: str) -> None:
    """Safely updates WEBAPP_URL in the project's .env file."""
    if not ENV_PATH.exists():
        logger.warning(f"⚠️ .env file not found at {ENV_PATH}")
        return

    content = ENV_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    new_lines = []

    for line in lines:
        if line.strip().startswith("WEBAPP_URL="):
            new_lines.append(f"WEBAPP_URL={new_url}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"WEBAPP_URL={new_url}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    logger.info(f"💾 Updated WEBAPP_URL in .env -> {new_url}")


def run_daemon() -> None:
    """Launches pyngrok HTTPS tunnel and keeps process alive."""
    from pyngrok import ngrok

    print("🚀 Initializing Ngrok HTTPS Tunnel Service...")

    if NGROK_AUTHTOKEN:
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
        print("🔑 Applied Ngrok Authtoken from environment.")
    else:
        print("⚠️ Warning: NGROK_AUTHTOKEN not set in .env. Running in unauthenticated mode.")

    tunnel = None
    try:
        tunnel = ngrok.connect(HTTP_PORT, "http")
        public_url = tunnel.public_url.replace("http://", "https://")
        print(f"\n✨ Ngrok HTTPS Tunnel Active: {public_url}")
        print(f"🔗 Forwarding -> http://localhost:{HTTP_PORT}\n")

        update_env_webapp_url(public_url)
        print("📌 Process running in background daemon mode. Press Ctrl+C to stop.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping Ngrok Tunnel daemon...")
    except Exception as err:
        print(f"❌ Ngrok Tunnel Error: {err}")
    finally:
        if tunnel:
            try:
                ngrok.disconnect(tunnel.public_url)
                ngrok.kill()
            except Exception:
                pass
        print("👋 Ngrok daemon stopped.")


if __name__ == "__main__":
    run_daemon()
