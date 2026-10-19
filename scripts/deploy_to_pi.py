import os
import paramiko
import sys
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def get_all_project_files():
    files = []
    extensions = ('.py', '.html', '.js', '.css', '.md')
    exclude_dirs = {'.venv', '__pycache__', '.git', 'logs', 'db', '.idea'}
    tracked_files = subprocess.run(
        ['git', 'ls-files', '--cached'],
        cwd=str(PROJECT_ROOT),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for file_path in tracked_files:
        normalized_path = file_path.replace("\\", "/")
        path_parts = normalized_path.split("/")
        if Path(normalized_path).suffix.lower() not in extensions:
            continue
        if any(part in exclude_dirs for part in path_parts):
            continue
        # The deploy helper only uploads files already in Git's index. This
        # prevents local debug dumps and credential-bearing scratch scripts
        # from being copied to the Raspberry Pi accidentally.
        files.append((file_path, normalized_path))
    return files

def deploy():
    pi_ip = os.environ.get("PI_IP", "192.168.1.47")
    username = os.environ.get("PI_USER", "host2")
    password = os.environ.get("PI_PASS")
    remote_dir = os.environ.get("PI_DIR", "/home/host2/bot_dir")

    files_to_sync = get_all_project_files()

    print(f"Connecting to Raspberry Pi at {pi_ip}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(pi_ip, username=username, password=password, timeout=10)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    print(f"Uploading {len(files_to_sync)} updated files via SFTP...")
    sftp = ssh.open_sftp()
    
    # Pre-create all necessary directories on the remote
    dirs_to_create = set(os.path.dirname(remote_path) for _, remote_path in files_to_sync if os.path.dirname(remote_path))
    for d in sorted(list(dirs_to_create)):
        if d:
            try:
                ssh.exec_command(f"mkdir -p {remote_dir}/{d}")
            except Exception:
                pass

    for local_path, relative_remote_path in files_to_sync:
        remote_path = f"{remote_dir}/{relative_remote_path}"
        sftp.put(str(PROJECT_ROOT / local_path), remote_path)
    sftp.close()
    print("[OK] Files uploaded.")

    print("Restarting tgbot.service on Raspberry Pi...")
    stdin, stdout, stderr = ssh.exec_command(f"echo {password} | sudo -S systemctl restart tgbot")
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("[OK] tgbot.service successfully restarted.")
    else:
        print(f"[WARN] Service restart returned status: {exit_status}")
        print(stderr.read().decode('utf-8', errors='ignore'))

    ssh.close()
    print("[DONE] Deployment finished successfully!")

if __name__ == "__main__":
    deploy()
