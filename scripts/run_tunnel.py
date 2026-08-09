"""
Keep-alive wrapper for HTTPS Tunneling service.
Auto-restarts localtunnel if disconnected.
"""
import sys
import subprocess
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    print("Starting persistent HTTPS localtunnel on port 8080...")
    cmd = ["cmd", "/c", "npx -y localtunnel --port 8080 --subdomain my3dfarmbot"]
    
    while True:
        try:
            print(f"Launching localtunnel process: {' '.join(cmd)}")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
            proc.wait()
            print("Tunnel process exited. Reconnecting in 3 seconds...")
        except Exception as e:
            print(f"Tunnel error: {e}. Retrying in 5 seconds...")
        time.sleep(3)

if __name__ == "__main__":
    main()
