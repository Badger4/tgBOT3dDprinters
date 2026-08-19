"""
FTPS client and G-Code / 3MF filament weight parser for Bambu Lab printers.
"""

import ftplib
import io
import re
import socket
import ssl
import zipfile
from typing import Any

from config import logger


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS subclass for implicit SSL/TLS on port 990 for Bambu Lab printers."""

    def connect(self, host: str = "", port: int = 990, timeout: float = 10.0, source_address: Any | None = None) -> str:
        if host != "":
            self.host = host
        if port > 0:
            self.port = port
        self.timeout = timeout if timeout and timeout > 0 else 10.0
        self.sock = socket.create_connection((self.host, self.port), self.timeout, source_address)
        self.af = self.sock.family
        if not hasattr(self, "context") or self.context is None:
            self.context = ssl.create_default_context()
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE
        self.sock = self.context.wrap_socket(self.sock)
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return str(self.welcome)

    def ntransfercmd(self, cmd: str, rest: Any | None = None) -> Any:
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if getattr(self, "_prot_p", False):
            conn = self.context.wrap_socket(conn, server_hostname=None)
        return conn, size


class BambuFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS subclass for explicit SSL/TLS on port 21 for Bambu Lab printers."""

    def ntransfercmd(self, cmd: str, rest: Any | None = None) -> Any:
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if getattr(self, "_prot_p", False):
            conn = self.context.wrap_socket(conn, server_hostname=None)
        return conn, size


def extract_model_weight(print_data: dict[str, Any]) -> float:
    """Extracts model weight from Bambu Lab / OrcaSlicer MQTT payload or filename regex."""
    keys = [
        "filament_weight",
        "weight",
        "subtask_weight",
        "gcode_weight",
        "total_weight",
        "used_g",
        "model_weight",
        "extruder_weight_total",
        "exyride_weight_total",
        "extruder_weight",
        "filament_weight_total",
        "filament_used",
        "filament_used_g",
        "filament used [g]",
        "filament_used_[g]",
        "filament used",
        "total filament weight",
    ]
    for k in keys:
        if k in print_data and print_data[k] is not None:
            try:
                val = float(print_data[k])
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass

    def _search_dict(d: Any) -> float:
        if isinstance(d, dict):
            for k, v in d.items():
                if k in keys and v is not None:
                    try:
                        val = float(v)
                        if val > 0:
                            return val
                    except (ValueError, TypeError):
                        pass
                res = _search_dict(v)
                if res > 0:
                    return res
        elif isinstance(d, list):
            for item in d:
                res = _search_dict(item)
                if res > 0:
                    return res
        return 0.0

    res = _search_dict(print_data)
    if res > 0:
        return res

    subtask = str(print_data.get("subtask_name") or print_data.get("gcode_file") or "")
    if subtask:
        m = re.search(r"(?:_|\b)(\d+(?:[\.,]\d+)?)\s*(?:g|г|gram|grams)\b", subtask, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
                if val > 0:
                    return val
            except ValueError:
                pass

    return 0.0


def parse_weight_from_gcode_text(text: str) -> float:
    """Parses filament weight in grams from G-code text comments targeting 'filament used [g] ='."""
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean.startswith(";"):
            continue
        line_lower = line_clean.lower()

        # Look for weight comment keywords
        if any(
            k in line_lower
            for k in [
                "filament used [g]",
                "total filament used [g]",
                "filament weight",
                "total filament weight",
                "filament_weight_total",
                "extruder_weight_total",
                "filament_used_g",
                "filament_used",
                "weight [g]",
                "used_g",
            ]
        ):
            # Skip lines describing only [mm] length without weight
            if "[mm]" in line_lower and "[g]" not in line_lower and "weight" not in line_lower:
                continue

            after_eq = line_clean.split("=", 1)[-1] if "=" in line_clean else line_clean.split(":", 1)[-1]
            after_eq_clean = after_eq.split("(")[0]

            numbers = re.findall(r"\b\d+(?:[\.,]\d+)?\b", after_eq_clean)
            valid_weights = []
            for num_str in numbers:
                try:
                    val = float(num_str.replace(",", "."))
                    if 0.05 <= val <= 5000:
                        valid_weights.append(val)
                except ValueError:
                    pass

            if valid_weights:
                return round(sum(valid_weights), 2)

    return 0.0


def parse_weight_from_3mf_bytes(data_bytes: bytes) -> float:
    """Parses filament weight from 3MF zip container (slice_info.config or embedded .gcode)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data_bytes)) as zf:
            # 1. Try slice_info.config first
            for name in zf.namelist():
                if name.endswith("slice_info.config"):
                    try:
                        content = zf.read(name).decode("utf-8", errors="ignore")
                        m = re.search(r"(?:filament\s+used\s*\[g\]|used_g|filament_weight|weight)[^\d\.,]*([\d\.,]+)", content, re.IGNORECASE)
                        if m:
                            val = float(m.group(1).replace(",", "."))
                            if 0 < val < 5000:
                                return val
                    except Exception:
                        pass

            # 2. If not found in slice_info.config, search embedded .gcode files inside 3MF zip for 'filament used [g] ='
            for name in zf.namelist():
                if name.endswith(".gcode"):
                    try:
                        gcode_txt = zf.read(name).decode("utf-8", errors="ignore")
                        w = parse_weight_from_gcode_text(gcode_txt)
                        if w > 0:
                            return w
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"❌ 3MF zip parse error: {e}", exc_info=True)
    return 0.0


def _connect_bambu_ftps(ip: str, access_code: str, timeout: float = 10.0) -> Any:
    """Connects to Bambu Lab FTPS trying Port 990 (Implicit) then Port 21 (Explicit)."""
    ftps: Any = None
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ftps = ImplicitFTP_TLS(context=ctx)
        ftps.connect(ip, 990, timeout=timeout)
        ftps.login("bblp", access_code)
        ftps.prot_p()
        ftps.set_pasv(True)
        return ftps
    except (TimeoutError, ConnectionRefusedError):
        pass
    except Exception as e1:
        logger.debug(f"Port 990 FTPS attempt failed for {ip}: {e1}")

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ftps_bambu: Any = BambuFTP_TLS(context=ctx)
        ftps_bambu.ssl_version = ssl.PROTOCOL_TLSv1_2
        ftps_bambu.connect(ip, 21, timeout=timeout)

        ftps_bambu.login("bblp", access_code)
        ftps_bambu.prot_p()
        ftps_bambu.set_pasv(True)
        return ftps_bambu

    except (TimeoutError, ConnectionRefusedError):
        logger.info(f"ℹ️ FTPS port closed/disabled on {ip}.")
        return None
    except Exception as e2:
        logger.info(f"ℹ️ FTPS connection failed for {ip}: {e2}")
        return None


def fetch_bambu_ftps_weight(ip: str, access_code: str, target_filename: str = "") -> float:
    """Connects to Bambu Lab FTPS, downloads recent print file from SD card, and extracts weight."""
    if not ip or not access_code:
        return 0.0

    ftps = None
    try:
        ftps = _connect_bambu_ftps(ip, access_code)
        if not ftps:
            return 0.0

        files = []
        for folder in ["/", "/cache"]:
            try:
                flist = ftps.nlst(folder)
                for f in flist:
                    files.append(f)
            except Exception as e:
                logger.debug(f"FTPS nlst failed for {folder}: {e}")

        if not files:
            return 0.0

        candidate_files = [f for f in files if f.endswith(".3mf") or f.endswith(".gcode") or f.endswith(".gcode.3mf")]
        chosen_file = None
        if target_filename:
            clean_target = target_filename.lower().replace(".3mf", "").replace(".gcode", "")
            for c in candidate_files:
                if clean_target in c.lower():
                    chosen_file = c
                    break

        if not chosen_file and candidate_files:
            chosen_file = candidate_files[-1]

        if not chosen_file:
            return 0.0

        logger.info(f"📥 Downloading print file via FTPS from {ip}: {chosen_file}")
        buf = io.BytesIO()
        ftps.retrbinary(f"RETR {chosen_file}", buf.write)

        data_bytes = buf.getvalue()
        if not data_bytes:
            return 0.0

        if chosen_file.endswith(".3mf") or chosen_file.endswith(".gcode.3mf"):
            w = parse_weight_from_3mf_bytes(data_bytes)
            if w > 0:
                logger.info(f"✅ Extracted weight {w}g from 3MF via FTPS ({chosen_file})")
                return w

        txt = data_bytes.decode("utf-8", errors="ignore")
        w = parse_weight_from_gcode_text(txt)
        if w > 0:
            logger.info(f"✅ Extracted weight {w}g from Gcode via FTPS ({chosen_file})")
            return w

    except Exception as e:
        logger.error(f"❌ Bambu FTPS fetch error for {ip}: {e}", exc_info=True)
    finally:
        if ftps:
            try:
                ftps.quit()
            except Exception:
                pass

    return 0.0


def bambu_storbinary(ftps: ftplib.FTP, cmd: str, fp: io.BytesIO, blocksize: int = 8192) -> str:
    """
    Custom storbinary optimized for Bambu Lab MicroSD card write stability.
    Uses 8KB block size to prevent SD card buffer overflow and handles TLS socket teardown cleanly.
    """
    import time

    ftps.voidcmd("TYPE I")
    conn = ftps.transfercmd(cmd)
    try:
        while True:
            buf = fp.read(blocksize)
            if not buf:
                break
            conn.sendall(buf)
        # Small delay to allow TCP socket buffer to drain to printer RAM
        time.sleep(0.3)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Wait for 226 Transfer complete from Bambu printer
    resp = ftps.voidresp()
    # 2.0s post-upload delay so printer firmware finishes flushing FAT32 sectors to MicroSD card
    time.sleep(2.0)
    return resp


def sanitize_bambu_filename(filename: str) -> str:
    """
    Sanitizes filename for Bambu Lab FAT32 SD card filesystem:
    - Pure ASCII alphanumeric characters + underscores only
    - Short length (max 16 chars base name + extension)
    - Prevents SD card read/write exception [0500-C010311617]
    """
    import time

    ext = ".gcode" if filename.lower().endswith(".gcode") else ".3mf"
    raw_name = filename.rsplit(".", 1)[0]
    clean_base = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name)
    clean_base = re.sub(r"_+", "_", clean_base).strip("_")
    if not clean_base or len(clean_base) > 16:
        clean_base = f"print_{int(time.time()) % 100000}"
    return f"{clean_base}{ext}"


def upload_3mf_to_bambu(ip: str, access_code: str, file_bytes: bytes, filename: str) -> str | None:
    """
    Uploads a 3MF/Gcode file to Bambu Lab printer's SD card via FTPS.
    Returns remote relative filepath (e.g. 'cache/print_12345.3mf' or 'print_12345.3mf') on success, or None on failure.
    """
    import time

    if not ip or not access_code or not file_bytes:
        return None

    # Sanitize filename strictly for Bambu FAT32 SD card
    safe_fname = sanitize_bambu_filename(filename)
    logger.info(f"📤 Preparing FTPS upload to [{ip}] with sanitized filename: '{safe_fname}' ({len(file_bytes)} bytes)")

    # Attempt 1: Upload to /cache/
    ftps = _connect_bambu_ftps(ip, access_code, timeout=15.0)
    if ftps:
        try:
            in_cache = True
            try:
                ftps.cwd("/cache")
            except Exception:
                try:
                    ftps.mkd("/cache")
                    ftps.cwd("/cache")
                except Exception:
                    in_cache = False

            if in_cache:
                bambu_storbinary(ftps, f"STOR {safe_fname}", io.BytesIO(file_bytes), blocksize=8192)
                logger.info(f"✅ Uploaded 3MF file to /cache/{safe_fname} on [{ip}] via FTPS")
                return f"cache/{safe_fname}"
        except Exception as e_cache:
            logger.warning(f"FTPS upload to /cache failed for {ip}: {e_cache}")
        finally:
            try:
                time.sleep(1.0)
                ftps.quit()
            except Exception:
                pass

    # Attempt 2: Fresh connection upload to root /
    ftps_root = _connect_bambu_ftps(ip, access_code, timeout=15.0)
    if ftps_root:
        try:
            ftps_root.cwd("/")
            bambu_storbinary(ftps_root, f"STOR {safe_fname}", io.BytesIO(file_bytes), blocksize=8192)
            logger.info(f"✅ Uploaded 3MF file to /{safe_fname} on [{ip}] via FTPS")
            return safe_fname
        except Exception as e_root:
            logger.error(f"FTPS upload to root failed for {ip}: {e_root}")
        finally:
            try:
                time.sleep(1.0)
                ftps_root.quit()
            except Exception:
                pass

    return None
