"""
scripts/deploy_to_pi.py
Production-grade deployment and operations tool for 3D Printer Farm Bot on Raspberry Pi.

Features:
- Dual deployment modes: Git pull (default, fast) or SFTP sync (for uncommitted/offline work)
- Safe credential fallback (Environment variables -> Defaults -> CLI args)
- Remote pre-flight bytecode compilation (compileall) to prevent downtime from SyntaxError
- Systemd service lifecycle management (tgbot.service)
- Automated HTTP REST health check (GET /health)
- Remote journalctl inspection and error surfacing
- Operational diagnostic modes (--status-only, --logs-only)
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import paramiko

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Defaults matching production Raspberry Pi environment
DEFAULT_HOST = os.environ.get("PI_HOST") or os.environ.get("PI_IP") or "192.168.1.47"
DEFAULT_USER = os.environ.get("PI_USER", "host2")
DEFAULT_PASS = os.environ.get("PI_PASS", "ADM82172")
DEFAULT_DIR = os.environ.get("PI_DIR", "/home/host2/bot_dir")
DEFAULT_SERVICE = os.environ.get("PI_SERVICE", "tgbot")
DEFAULT_PORT = int(os.environ.get("PI_PORT", "22"))


def get_ssh_client(host: str, port: int, user: str, password: str | None, timeout: int = 12) -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=port, username=user, password=password, timeout=timeout)
        return ssh
    except Exception as e:
        print(f"❌ [SSH Connection Error] Could not connect to {user}@{host}:{port}: {e}")
        sys.exit(1)


def run_remote_command(ssh: paramiko.SSHClient, cmd: str, sudo_pass: str | None = None) -> tuple[int, str, str]:
    if sudo_pass and "sudo -S" in cmd:
        full_cmd = f"echo '{sudo_pass}' | {cmd}"
    else:
        full_cmd = cmd
    stdin, stdout, stderr = ssh.exec_command(full_cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return exit_code, out, err


def get_tracked_files():
    extensions = (".py", ".html", ".js", ".css", ".md", ".json", ".txt", ".service", ".conf")
    exclude_dirs = {".venv", "venv", "__pycache__", ".git", "logs", "scratch", "tools", ".idea"}
    res = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=str(PROJECT_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    files = []
    for line in res.stdout.splitlines():
        norm = line.replace("\\", "/")
        parts = norm.split("/")
        if Path(norm).suffix.lower() not in extensions:
            continue
        if any(p in exclude_dirs for p in parts):
            continue
        files.append((line, norm))
    return files


def deploy_via_git(ssh: paramiko.SSHClient, remote_dir: str, branch: str) -> bool:
    print(f"🔄 Executing remote git pull (branch: {branch})...")
    code, out, err = run_remote_command(
        ssh, f"cd {remote_dir} && git fetch origin && git checkout {branch} && git pull origin {branch}"
    )
    if out:
        print(out)
    if err and "error:" in err.lower():
        print(f"❌ Git pull encountered an error:\n{err}")
        return False

    code, head_out, _ = run_remote_command(ssh, f"cd {remote_dir} && git log -n 1 --oneline")
    print(f"📌 Active Commit on Pi: {head_out}")
    return True


def deploy_via_sftp(ssh: paramiko.SSHClient, remote_dir: str):
    files = get_tracked_files()
    print(f"📦 Uploading {len(files)} tracked files via SFTP...")
    sftp = ssh.open_sftp()
    dirs = sorted(list(set(os.path.dirname(r) for _, r in files if os.path.dirname(r))))
    for d in dirs:
        run_remote_command(ssh, f"mkdir -p {remote_dir}/{d}")
    for local_rel, remote_rel in files:
        sftp.put(str(PROJECT_ROOT / local_rel), f"{remote_dir}/{remote_rel}")
    sftp.close()
    print("✅ SFTP upload complete.")


def run_preflight_compilation(ssh: paramiko.SSHClient, remote_dir: str) -> bool:
    print("🔍 Running pre-flight bytecode compilation check on Raspberry Pi...")
    code, out, err = run_remote_command(ssh, f"python3 -m compileall -q {remote_dir}")
    if err and "SyntaxError" in err:
        print(f"🚨 CRITICAL: SyntaxError detected during remote compileall check!\n{err}")
        print("❌ ABORTING restart to prevent service downtime!")
        return False
    print("✅ Pre-flight compilation check PASSED.")
    return True


def restart_and_validate(ssh: paramiko.SSHClient, service: str, password: str, wait_secs: int = 4) -> bool:
    print(f"🔄 Restarting {service}.service...")
    code, out, err = run_remote_command(ssh, f"sudo -S systemctl restart {service}", sudo_pass=password)
    if code != 0:
        print(f"❌ Failed to restart {service}.service (exit code {code}):\n{err}")
        return False

    print(f"⏳ Waiting {wait_secs}s for bot and REST API to initialize...")
    time.sleep(wait_secs)

    # 1. Systemd status
    print(f"📊 Checking {service}.service status...")
    code, out, _ = run_remote_command(ssh, f"systemctl status {service} --no-pager")
    print(out)

    # 2. HTTP Health Probe
    print("🏥 Probing REST health endpoint (http://127.0.0.1:8080/health)...")
    code, health_out, _ = run_remote_command(ssh, "curl -s -i http://127.0.0.1:8080/health")
    if "200 OK" in health_out or '"status": "ok"' in health_out:
        print(f"✅ REST API health check PASSED:\n{health_out}")
    else:
        print(f"ℹ️ Health probe response:\n{health_out}")

    # 3. Journal logs
    print(f"📜 Recent journal logs ({service}):")
    code, logs_out, _ = run_remote_command(ssh, f"sudo -S journalctl -u {service} -n 20 --no-pager", sudo_pass=password)
    print(logs_out)
    return True


def main():
    parser = argparse.ArgumentParser(description="Production deployment tool for 3D Printer Farm Bot")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Raspberry Pi IP address or hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="SSH port")
    parser.add_argument("--user", default=DEFAULT_USER, help="SSH username")
    parser.add_argument("--password", default=DEFAULT_PASS, help="SSH / sudo password")
    parser.add_argument("--dir", default=DEFAULT_DIR, help="Remote project directory")
    parser.add_argument("--service", default=DEFAULT_SERVICE, help="Systemd service name")
    parser.add_argument("--method", choices=["git", "sftp"], default="git", help="Deployment method (default: git)")
    parser.add_argument("--branch", default="main", help="Git branch to pull (for --method git)")
    parser.add_argument("--skip-compile", action="store_true", help="Skip remote compileall verification")
    parser.add_argument("--no-restart", action="store_true", help="Sync files without restarting service")
    parser.add_argument("--status-only", action="store_true", help="Only check service status and health")
    parser.add_argument("--logs-only", action="store_true", help="Tail recent journalctl logs and exit")

    args = parser.parse_args()

    print(f"🚀 Connecting to {args.user}@{args.host}:{args.port}...")
    ssh = get_ssh_client(args.host, args.port, args.user, args.password)

    try:
        if args.status_only:
            _, out, _ = run_remote_command(ssh, f"systemctl status {args.service} --no-pager")
            print(out)
            _, health, _ = run_remote_command(ssh, "curl -s -i http://127.0.0.1:8080/health")
            print(health)
            return

        if args.logs_only:
            _, logs, _ = run_remote_command(
                ssh, f"sudo -S journalctl -u {args.service} -n 35 --no-pager", sudo_pass=args.password
            )
            print(logs)
            return

        # Deploy code
        if args.method == "git":
            if not deploy_via_git(ssh, args.dir, args.branch):
                sys.exit(1)
        else:
            deploy_via_sftp(ssh, args.dir)

        # Pre-flight compilation check
        if not args.skip_compile:
            if not run_preflight_compilation(ssh, args.dir):
                sys.exit(1)

        # Restart and validate
        if not args.no_restart:
            restart_and_validate(ssh, args.service, args.password)

        print("\n🎉 [DONE] Deployment completed successfully!")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
