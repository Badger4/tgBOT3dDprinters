"""
Ngrok HTTPS Tunnel Runner Script for Telegram WebApp SPA.
Configures pyngrok auth token, opens an HTTPS tunnel to local HTTP_PORT,
and automatically updates WEBAPP_URL in .env.
"""

import sys
import time
from pathlib import Path
from typing import Any

# Add project root directory to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from urllib.parse import urlparse

import config
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


def start_ngrok_tunnel(
    port: int = HTTP_PORT, authtoken: str | None = NGROK_AUTHTOKEN, domain: str | None = None
) -> Any:
    """Launches pyngrok HTTPS tunnel with static domain binding, updates .env, and returns the tunnel object."""
    from pyngrok import ngrok

    logger.info(f"🚀 Initializing Ngrok HTTPS Tunnel Service on port {port}...")

    if authtoken:
        try:
            ngrok.set_auth_token(authtoken)
            logger.info("🔑 Applied Ngrok Authtoken from environment.")
        except Exception as e:
            logger.warning(f"Failed setting Ngrok authtoken: {e}")
    else:
        logger.warning("⚠️ NGROK_AUTHTOKEN not provided. Running in unauthenticated mode.")

    target_domain = domain or getattr(config, "NGROK_DOMAIN", "") or ""
    if not target_domain and "ngrok" in getattr(config, "WEBAPP_URL", ""):
        parsed = urlparse(getattr(config, "WEBAPP_URL", ""))
        if parsed.netloc:
            target_domain = parsed.netloc

    connect_kwargs: dict[str, Any] = {}
    if target_domain:
        clean_domain = target_domain.replace("https://", "").replace("http://", "").split("/")[0].strip()
        connect_kwargs["domain"] = clean_domain
        logger.info(f"📌 Requesting Ngrok Static Domain: {clean_domain}")

    try:
        tunnel = ngrok.connect(port, "http", **connect_kwargs)
    except Exception as err:
        if target_domain:
            logger.warning(f"⚠️ Failed connecting with static domain '{target_domain}': {err}. Retrying without domain...")
            tunnel = ngrok.connect(port, "http")
        else:
            raise err

    public_url = str(getattr(tunnel, "public_url", "")).replace("http://", "https://")
    logger.info(f"✨ Ngrok HTTPS Tunnel Active: {public_url}")
    update_env_webapp_url(public_url)
    return tunnel


def stop_ngrok_tunnel(tunnel: Any | None = None) -> None:
    """Safely disconnects and kills pyngrok tunnel process."""
    from pyngrok import ngrok

    if tunnel:
        try:
            public_url = getattr(tunnel, "public_url", None)
            if public_url:
                ngrok.disconnect(public_url)
        except Exception as e:
            logger.warning(f"Error disconnecting ngrok tunnel: {e}")
    try:
        ngrok.kill()
    except Exception as e:
        logger.warning(f"Error killing ngrok process: {e}")
    logger.info("👋 Ngrok tunnel stopped.")


def run_daemon() -> None:
    """Launches pyngrok HTTPS tunnel and keeps process alive for CLI usage."""
    tunnel = None
    try:
        tunnel = start_ngrok_tunnel(HTTP_PORT, NGROK_AUTHTOKEN)
        print(f"\n✨ Ngrok HTTPS Tunnel Active: {getattr(tunnel, 'public_url', '')}")
        print(f"🔗 Forwarding -> http://localhost:{HTTP_PORT}\n")
        print("📌 Process running in background daemon mode. Press Ctrl+C to stop.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping Ngrok Tunnel daemon...")
    except Exception as err:
        print(f"❌ Ngrok Tunnel Error: {err}")
    finally:
        stop_ngrok_tunnel(tunnel)


if __name__ == "__main__":
    run_daemon()
