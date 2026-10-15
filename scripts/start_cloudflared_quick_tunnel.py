#!/usr/bin/env python3
"""Run a Cloudflare Quick Tunnel and keep the bot URL in sync with it."""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_DIR / ".env"
URL_STATE_FILE = PROJECT_DIR / ".cloudflared_quick_url"
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
STOP = False
CHILD: subprocess.Popen[str] | None = None


def log(message: str) -> None:
    print(f"cloudflared-quick-wrapper: {message}", flush=True)


def notify_systemd(message: str) -> None:
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return
    address = "\0" + notify_socket[1:] if notify_socket.startswith("@") else notify_socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(message.encode("utf-8"))
    except OSError as exc:
        log(f"systemd notification failed: {exc}")


def update_web_urls(url: str) -> bool:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    updates = {
        "WEBAPP_URL": url,
        "WEBHOOK_URL": url,
        "AUTO_NGROK": "false",
        "DISABLE_NGROK": "true",
    }
    output: list[str] = []
    found: set[str] = set()
    for line in lines:
        key, separator, _value = line.partition("=")
        if separator and key in updates:
            if key not in found:
                output.append(f"{key}={updates[key]}")
                found.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in found:
            output.append(f"{key}={value}")

    temporary = ENV_FILE.with_name(".env.quick-tunnel.tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(ENV_FILE)
    return True


def restart_bot_if_running() -> None:
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "tgbot.service"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if active.returncode != 0:
        return
    result = subprocess.run(
        ["sudo", "-n", "systemctl", "try-restart", "tgbot.service"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        log("could not restart tgbot.service after the Quick Tunnel URL changed")
    else:
        log("restarted tgbot.service for the new WebApp and webhook URL")


def handle_url(url: str, ready: bool) -> bool:
    previous = URL_STATE_FILE.read_text(encoding="utf-8").strip() if URL_STATE_FILE.exists() else ""
    if url == previous:
        # Keep .env correct even if it was edited or restored independently.
        update_web_urls(url)
        return ready

    update_web_urls(url)
    URL_STATE_FILE.write_text(url + "\n", encoding="utf-8")
    URL_STATE_FILE.chmod(0o600)
    log(f"Quick Tunnel URL is {url}")

    if not ready:
        notify_systemd(f"READY=1\nSTATUS=Quick Tunnel ready: {url}")
        # On boot the ordered bot service is not active yet (try-restart is a
        # no-op). If the tunnel alone was restarted manually, refresh the bot.
        restart_bot_if_running()
        return True

    notify_systemd(f"STATUS=Quick Tunnel URL changed: {url}")
    restart_bot_if_running()
    return True


def stop_child(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True
    if CHILD and CHILD.poll() is None:
        CHILD.terminate()


def main() -> int:
    global CHILD
    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)
    ready = False
    retry_delay = 3

    while not STOP:
        log("starting Quick Tunnel for http://localhost:8080")
        try:
            CHILD = subprocess.Popen(
                ["/usr/local/bin/cloudflared", "tunnel", "--url", "http://localhost:8080"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            log(f"could not start cloudflared: {exc}")
            time.sleep(retry_delay)
            continue

        assert CHILD.stdout is not None
        for line in CHILD.stdout:
            print(line, end="", flush=True)
            match = TUNNEL_URL_RE.search(line)
            if match:
                ready = handle_url(match.group(0).rstrip("."), ready)

        return_code = CHILD.wait()
        CHILD = None
        if STOP:
            break
        log(f"cloudflared exited with status {return_code}; retrying in {retry_delay}s")
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
