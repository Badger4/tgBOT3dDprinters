"""
Cross-platform system health telemetry for Raspberry Pi (Linux) and Windows/macOS.
Provides CPU temperature, RAM usage, SD/Disk free space, and Wi-Fi signal strength.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
from pathlib import Path
from typing import Any


def get_cpu_temp_c() -> float | None:
    """Reads CPU temperature in Celsius from Linux thermal_zone0 (Raspberry Pi)."""
    thermal_paths = [
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/devices/virtual/thermal/thermal_zone0/temp"),
    ]
    for p in thermal_paths:
        try:
            if p.exists():
                raw = p.read_text(encoding="utf-8").strip()
                if raw:
                    val = float(raw)
                    return round(val / 1000.0 if val > 200 else val, 1)
        except Exception:
            pass
    return None


def get_ram_usage() -> dict[str, Any]:
    """Returns RAM usage dictionary: used_mb, total_mb, pct."""
    # 1. Linux (/proc/meminfo)
    meminfo_path = Path("/proc/meminfo")
    if meminfo_path.exists():
        try:
            info: dict[str, int] = {}
            for line in meminfo_path.read_text(encoding="utf-8").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    parts = v.strip().split()
                    if parts and parts[0].isdigit():
                        info[k.strip()] = int(parts[0])  # in kB
            total_kb = info.get("MemTotal", 0)
            avail_kb = info.get("MemAvailable", info.get("MemFree", 0) + info.get("Buffers", 0) + info.get("Cached", 0))
            if total_kb > 0:
                used_kb = max(0, total_kb - avail_kb)
                total_mb = round(total_kb / 1024)
                used_mb = round(used_kb / 1024)
                pct = round((used_kb / total_kb) * 100.0, 1)
                return {"used_mb": used_mb, "total_mb": total_mb, "pct": pct}
        except Exception:
            pass

    # 2. Windows fallback via ctypes GlobalMemoryStatusEx
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            windll = getattr(ctypes, "windll", None)
            if windll and windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_mb = round(stat.ullTotalPhys / (1024 * 1024))
                avail_mb = round(stat.ullAvailPhys / (1024 * 1024))
                used_mb = max(0, total_mb - avail_mb)
                pct = round(float(stat.dwMemoryLoad), 1)
                return {"used_mb": used_mb, "total_mb": total_mb, "pct": pct}
        except Exception:
            pass

    return {"used_mb": 0, "total_mb": 0, "pct": 0.0}


def get_disk_usage(target_path: str | Path | None = None) -> dict[str, Any]:
    """Returns disk usage dictionary: free_gb, total_gb, used_gb, pct."""
    try:
        check_path = Path(target_path) if target_path else Path(__file__).resolve().parent
        usage = shutil.disk_usage(check_path)
        total_gb = round(usage.total / (1024**3), 1)
        free_gb = round(usage.free / (1024**3), 1)
        used_gb = round(usage.used / (1024**3), 1)
        pct = round((usage.used / usage.total) * 100.0, 1) if usage.total > 0 else 0.0
        return {"free_gb": free_gb, "total_gb": total_gb, "used_gb": used_gb, "pct": pct}
    except Exception:
        return {"free_gb": 0.0, "total_gb": 0.0, "used_gb": 0.0, "pct": 0.0}


def get_wifi_signal_dbm() -> int | None:
    """Reads Wi-Fi signal level (dBm) from /proc/net/wireless on Linux if available."""
    wireless_path = Path("/proc/net/wireless")
    if wireless_path.exists():
        try:
            lines = wireless_path.read_text(encoding="utf-8").splitlines()
            for line in lines[2:]:
                parts = line.split()
                if len(parts) >= 4:
                    raw_level = parts[3].rstrip(".")
                    val = int(float(raw_level))
                    return val
        except Exception:
            pass
    return None


def get_system_health() -> dict[str, Any]:
    """Collects all system health metrics for Raspberry Pi / host server."""
    cpu_temp = get_cpu_temp_c()
    ram = get_ram_usage()
    disk = get_disk_usage()
    wifi_dbm = get_wifi_signal_dbm()

    return {
        "platform": platform.system(),
        "cpu_temp_c": cpu_temp,
        "ram_used_mb": ram["used_mb"],
        "ram_total_mb": ram["total_mb"],
        "ram_pct": ram["pct"],
        "disk_free_gb": disk["free_gb"],
        "disk_total_gb": disk["total_gb"],
        "disk_pct": disk["pct"],
        "wifi_signal_dbm": wifi_dbm,
    }
