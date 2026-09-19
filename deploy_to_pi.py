import os
import paramiko
import sys

def deploy():
    pi_ip = os.environ.get("PI_IP", "192.168.1.47")
    username = os.environ.get("PI_USER", "host2")
    password = os.environ.get("PI_PASS", "ADM82172")
    remote_dir = os.environ.get("PI_DIR", "/home/host2/bot_dir")

    files_to_sync = [
        ("models/printer.py", f"{remote_dir}/models/printer.py"),
        ("utils/filament_utils.py", f"{remote_dir}/utils/filament_utils.py"),
        ("bot/handlers/printers/view.py", f"{remote_dir}/bot/handlers/printers/view.py"),
        ("bot/handlers/filament/view.py", f"{remote_dir}/bot/handlers/filament/view.py"),
        ("bot/handlers/filament/mount.py", f"{remote_dir}/bot/handlers/filament/mount.py"),
        ("bot/keyboards.py", f"{remote_dir}/bot/keyboards.py"),
        ("PROJECT_STRUCTURE.md", f"{remote_dir}/PROJECT_STRUCTURE.md"),
        ("webapp/index.html", f"{remote_dir}/webapp/index.html"),
        ("webapp/static/js/app.js", f"{remote_dir}/webapp/static/js/app.js"),
        ("tests/test_ams_orcaslicer_integration.py", f"{remote_dir}/tests/test_ams_orcaslicer_integration.py"),
        ("tests/test_printer_status_card.py", f"{remote_dir}/tests/test_printer_status_card.py"),
        ("tests/test_filament_hardware_sync.py", f"{remote_dir}/tests/test_filament_hardware_sync.py"),
        ("tests/test_filament_comprehensive_workflow.py", f"{remote_dir}/tests/test_filament_comprehensive_workflow.py"),
        ("tests/test_ams_auto_detection.py", f"{remote_dir}/tests/test_ams_auto_detection.py"),
    ]

    print(f"Connecting to Raspberry Pi at {pi_ip}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(pi_ip, username=username, password=password, timeout=10)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("💡 Переконайтеся, що ПК підключено до тієї ж Wi-Fi мережі, що й Raspberry Pi (192.168.1.x)!")
        sys.exit(1)

    print("Uploading updated files via SFTP...")
    sftp = ssh.open_sftp()
    for local_path, remote_path in files_to_sync:
        print(f"  -> Uploading {local_path} to {remote_path}...")
        sftp.put(local_path, remote_path)
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

    stdin, stdout, stderr = ssh.exec_command("systemctl status tgbot --no-pager")
    status_out = stdout.read().decode('utf-8', errors='ignore')
    try:
        print(status_out)
    except UnicodeEncodeError:
        print(status_out.encode('ascii', errors='replace').decode('ascii'))

    ssh.close()
    print("[DONE] Deployment finished successfully!")

if __name__ == "__main__":
    deploy()
