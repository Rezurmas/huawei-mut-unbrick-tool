#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unbrick_tool.py - Huawei MUT Unbrick Tool (community edition)
==============================================================
ALL-IN-ONE narzedzie do unbrick'a routerow Huawei przez protokol
Multicast Upgrade Tool (MUT). Rewrite od zera z GUI Tkinter,
maksymalnymi zabezpieczeniami i pelna dokumentacja protokolu.

Reverse-engineered z HuaweiMUT.exe (389120B, MFC VC6, build 2008-05-15).
Plus internet research: blog.hqcodeshop.fi (Jari Turkia E5186), 4PDA, XDA.

Modele wspierane:
  - WS7200 / AX3 Pro       (Hi5651T, secure boot - software recovery NIEMOZLIWE)
  - WS7100 / AX3           (j.w.)
  - Honor Router 3 / XD-20 (j.w.)
  - E5186 LTE              (slabszy bootloader - dziala)
  - B315 / B525 / B535 LTE
  - HG630V2 DSL
  - HG633 / HG659 DSL

WAZNE:
  Dla WS7200/AX3/Honor R3 secure boot w silicon (Hi5651T) odrzuca
  unsigned firmware. Software recovery niemozliwa - patrz
  _research/FINAL_REPORT.md, _research/PLAN_A_UART_RECOVERY.md.

Uzycie:
  python unbrick_tool.py            # GUI (default)
  python unbrick_tool.py --cli ...  # CLI mode (jak mut_python.py)
  python unbrick_tool.py --gen-ini firmware.bin
  python unbrick_tool.py --list-adapters

Wymagania:
  Python >= 3.7 (built-in tkinter)
  Windows (uzywa ipconfig, netsh, powershell)
  Administrator (bind port 13456)

License: MIT (community release)
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import datetime
import ipaddress
import json
import logging
import os
import queue
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Tkinter - core (built-in)
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False


# ============================================================================
# 1. CONSTANTS (z reverse engineering)
# ============================================================================
APP_VERSION = "1.0.0"
APP_NAME = "Huawei MUT Unbrick Tool"

# Network protocol
MULTICAST_IP        = "224.0.0.119"
MULTICAST_PORT      = 13456            # 0x3490
PACKET_SIZE         = 1086
HEADER_SIZE         = 62
CHUNK_SIZE          = 1024             # 0x400
# *** CRITICAL ***: 5ms = z conf.dat oryginalnego MUT (INTERVAL_TIME=5ms).
# Guide.txt z 4PDA: "put '2' for successful firmware! You can also put '5'!"
# 200ms (jak bylo wczesniej) = 100x za wolno -> router timeout, flash failuje!
DEFAULT_INTERVAL_MS = 5
DEFAULT_TTL         = 0                # local segment only
DEFAULT_ROUTER_IP_AFTER_FLASH = "192.168.1.1"  # post-flash router IP (debug fw)

# Opcodes (control_word = (opcode << 29) | 0x400)
OPCODE_DATA = 1
OPCODE_LAST = 2
OPCODE_INIT = 4

CTRL_DATA = (OPCODE_DATA << 29) | 0x400  # 0x20000400
CTRL_LAST = (OPCODE_LAST << 29) | 0x400  # 0x40000400
CTRL_INIT = (OPCODE_INIT << 29) | 0x400  # 0x80000400

# Firmware magic (Huawei header offset 0x4)
HUAWEI_MAGIC = b'\x1a\xf0\x0f\x1a'

# Default INI fields
DEFAULT_PACKAGE_ID       = "fnt-HGW"
DEFAULT_PRODUCT_ID       = "fnt-HGW"
DEFAULT_FIRMWARE_VERSION = "0"
DEFAULT_PCB_VERSION      = "0"
PARTITIONS_NORMAL    = "CFE,0x00000000-0x0000FFFF,uncover|kernelfs,0x00010000-0x003FFFFF,cover"
PARTITIONS_FORCE_CFE = "CFE,0x00000000-0x0000FFFF,cover|kernelfs,0x00010000-0x003FFFFF,cover"

# Safety limits
MAX_PASSES_DEFAULT     = 30            # Z 5ms interval kazda runda ~3min, 30 = ~90min budget
WATCHDOG_TIMEOUT_SEC   = 60 * 60       # 60 minut max (bezpieczenstwo)
LINK_CHECK_INTERVAL    = 5             # co 5s sprawdz link
ROUTER_PING_CACHE_SEC  = 3             # cache ping result na 3s (zeby nie blokowac GUI)

# Inne adaptery do auto-disable przed flashem (jak _flash_prepare.ps1)
ADAPTERS_TO_DISABLE = ['Wi-Fi', 'Tailscale', 'Bluetooth Network Connection',
                       'WireGuard', 'OpenVPN TAP-Windows6', 'OpenVPN Wintun']


# ============================================================================
# 2. MODEL PRESETS
# ============================================================================
@dataclass
class ModelPreset:
    name: str
    soc: str
    router_ip: str
    pc_ip: str
    subnet_prefix: int = 24
    upgrade_trigger: str = ""
    firmware_format: str = ".bin"
    package_id: str = DEFAULT_PACKAGE_ID
    product_id: str = DEFAULT_PRODUCT_ID
    default_partitions: str = PARTITIONS_NORMAL
    secure_boot: bool = False           # Czy ma silicon-level signature check
    notes: str = ""


MODELS: Dict[str, ModelPreset] = {
    "WS7200 / AX3 Pro": ModelPreset(
        name="WS7200 / AX3 Pro",
        soc="HiSilicon Hi5651T",
        router_ip="192.168.3.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="trzymaj przycisk H + zasilanie",
        package_id="fnt-HGW",
        product_id="fnt-HGW",
        default_partitions=PARTITIONS_NORMAL,
        secure_boot=True,
        notes="UWAGA: Secure boot w silicon - software recovery NIEMOZLIWE. "
              "Tool wysle pakiety, ale router je odrzuci. Patrz FINAL_REPORT.md."
    ),
    "WS7100 / AX3 (Global)": ModelPreset(
        name="WS7100 / AX3",
        soc="HiSilicon Hi5651T",
        router_ip="192.168.3.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="trzymaj przycisk H + zasilanie",
        package_id="fnt-HGW",
        product_id="fnt-HGW",
        default_partitions=PARTITIONS_NORMAL,
        secure_boot=True,
        notes="Slabszy CPU niz WS7200. Tez secure boot."
    ),
    "Honor Router 3 / XD-20": ModelPreset(
        name="Honor Router 3 / XD-20",
        soc="HiSilicon Hi5651T",
        router_ip="192.168.3.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="trzymaj przycisk H + zasilanie",
        package_id="fnt-HGW",
        product_id="fnt-HGW",
        default_partitions=PARTITIONS_NORMAL,
        secure_boot=True,
        notes="Ten sam SoC co WS7200. Secure boot."
    ),
    "E5186 (LTE Cat.6)": ModelPreset(
        name="E5186",
        soc="HiSilicon Balong (LTE)",
        router_ip="192.168.8.1",
        pc_ip="192.168.8.100",
        upgrade_trigger="trzymaj WPS+WiFi, wlacz power, pusc WiFi w 0.85-1.89s",
        firmware_format=".gz.bin",
        package_id="mbb-CPE",
        product_id="mbb-CPE",
        secure_boot=False,
        notes="Slabszy bootloader. Jari Turkia odzyskal cegle przez MUT. "
              "Firmware moze byc .gz.bin (gzipped) - nasz tool to obsluguje."
    ),
    "B315 (LTE)": ModelPreset(
        name="B315",
        soc="HiSilicon Balong",
        router_ip="192.168.8.1",
        pc_ip="192.168.8.100",
        upgrade_trigger="Reset+WPS przez 10s + power up",
        package_id="mbb-CPE",
        product_id="mbb-CPE",
        secure_boot=False,
        notes="LTE indoor router. Software recovery dziala."
    ),
    "B525 (LTE)": ModelPreset(
        name="B525",
        soc="HiSilicon Balong",
        router_ip="192.168.8.1",
        pc_ip="192.168.8.100",
        upgrade_trigger="Reset+WPS przez 10s + power up",
        package_id="mbb-CPE",
        product_id="mbb-CPE",
        secure_boot=False,
        notes="LTE indoor router. Software recovery dziala."
    ),
    "B535 (LTE)": ModelPreset(
        name="B535",
        soc="HiSilicon Balong",
        router_ip="192.168.8.1",
        pc_ip="192.168.8.100",
        upgrade_trigger="Reset+WPS przez 10s + power up",
        package_id="mbb-CPE",
        product_id="mbb-CPE",
        secure_boot=False,
        notes="UWAGA: B535 wymaga matching signed firmware (modem+WebUI pair). "
              "C-version mismatch = brick! Zob. elektroda thread."
    ),
    "HG630V2 (DSL)": ModelPreset(
        name="HG630V2",
        soc="Broadcom",
        router_ip="192.168.1.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="Reset 30s + power up",
        firmware_format="multicast_restore_default_pack.bin",
        package_id="dsl-IAD",
        product_id="dsl-IAD",
        secure_boot=False,
        notes="DSL modem. Wymaga special 'multicast_restore_default_pack.bin'."
    ),
    "HG633 (DSL)": ModelPreset(
        name="HG633",
        soc="Lantiq",
        router_ip="192.168.1.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="Reset + power up",
        package_id="dsl-IAD",
        product_id="dsl-IAD",
        secure_boot=False,
        notes="DSL modem. Sa UART recovery procedury (jcjc-dev.com)."
    ),
    "HG659 (DSL)": ModelPreset(
        name="HG659",
        soc="HiSilicon",
        router_ip="192.168.1.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="Reset + power up",
        package_id="dsl-IAD",
        product_id="dsl-IAD",
        secure_boot=False,
        notes="DSL modem."
    ),
    "Custom (manual config)": ModelPreset(
        name="Custom",
        soc="Unknown",
        router_ip="192.168.1.1",
        pc_ip="192.168.1.5",
        upgrade_trigger="manual",
        package_id="",
        product_id="",
        default_partitions="",
        secure_boot=False,
        notes="Dla nieznanych modeli - wpisz wszystko recznie z INI Twojego firmware'u."
    ),
}


# ============================================================================
# 3. LOGGING
# ============================================================================
def setup_logging(log_dir: Path = None) -> logging.Logger:
    """Setup file + console logging."""
    if log_dir is None:
        log_dir = Path.cwd()
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"_unbrick_log_{timestamp}.txt"

    logger = logging.getLogger("unbrick_tool")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler - DEBUG level
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(fh)

    # Console handler - INFO level
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(ch)

    logger.info(f"=== {APP_NAME} v{APP_VERSION} ===")
    logger.info(f"Log file: {log_file}")
    return logger


LOG = logging.getLogger("unbrick_tool")


# ============================================================================
# 4. HELPERS - CRC + INI
# ============================================================================
def crc32(data: bytes) -> int:
    """zlib CRC32 (compatible z generate_ini_file.py)."""
    return zlib.crc32(data) & 0xFFFFFFFF


def precise_sleep(ms: int) -> None:
    """High-precision sleep (busy-wait, jak QueryPerformanceCounter w MUT)."""
    if ms <= 0:
        return
    target = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < target:
        if ms >= 100:
            time.sleep(0.001)


def process_firmware_file(file_path: str) -> Tuple[int, int]:
    """Returns (file_size, crc32)."""
    with open(file_path, 'rb') as f:
        data = f.read()
    return len(data), crc32(data)


def check_firmware_magic(file_path: str) -> Tuple[bool, bytes]:
    """Sprawdz czy firmware ma Huawei magic 0x1AF00F1A na offset 0x4."""
    try:
        with open(file_path, 'rb') as f:
            f.seek(4)
            magic = f.read(4)
        return magic == HUAWEI_MAGIC, magic
    except Exception:
        return False, b''


def generate_ini_content(filename: str, filesize: int, firmware_crc: int,
                         force_cfe: bool = False,
                         package_id: str = DEFAULT_PACKAGE_ID,
                         product_id: str = DEFAULT_PRODUCT_ID,
                         firmware_version: str = DEFAULT_FIRMWARE_VERSION,
                         pcb_version: str = DEFAULT_PCB_VERSION,
                         partitions: str = None) -> str:
    """Generuje INI content z poprawnym INI_CRC_SUM."""
    if partitions is None:
        partitions = PARTITIONS_FORCE_CFE if force_cfe else PARTITIONS_NORMAL
    content = (
        "# autogenerated by unbrick_tool.py\n"
        "# do NOT modify this file\n"
        f"IMAGE_NAME={filename}\n"
        f"IMAGE_SIZE={filesize}\n"
        f"PACKAGE_ID={package_id}\n"
        f"PRODUCT_ID={product_id}\n"
        f"FIRMWARE_VERSION={firmware_version}\n"
        f"PCB_VERSION={pcb_version}\n"
        f"FIRMWARE_CRC_SUM={firmware_crc}\n"
        f"PARTITIONS={partitions}\n"
        "INI_CRC_SUM="
    )
    ini_crc = crc32(content.encode('ascii'))
    return content + str(ini_crc)


def parse_ini(ini_path: str) -> Dict[str, str]:
    """Parsuje INI w stylu MUT (key=value, ignore comments)."""
    fields = {}
    with open(ini_path, 'rb') as f:
        content = f.read()
    for raw_line in content.replace(b'\r\n', b'\n').split(b'\n'):
        line = raw_line.strip()
        if not line or line.startswith(b'#') or line.startswith(b'//'):
            continue
        if b'=' not in line:
            continue
        k, v = line.split(b'=', 1)
        try:
            fields[k.decode('ascii').strip()] = v.decode('ascii').strip()
        except UnicodeDecodeError:
            pass
    return fields


def parse_partitions(partitions_str: str) -> List[dict]:
    """Parsuje 'CFE,0x0-0xFFFF,cover|kernelfs,...' -> list of dicts."""
    parts = []
    for entry in partitions_str.split('|'):
        entry = entry.strip()
        if not entry:
            continue
        try:
            name, range_str, flag = entry.split(',', 2)
            start_str, end_str = range_str.split('-')
            parts.append({
                'name': name.strip(),
                'start': int(start_str, 16),
                'end': int(end_str, 16),
                'flag': flag.strip().lower(),
                'cover': flag.strip().lower() == 'cover',
            })
        except (ValueError, IndexError):
            LOG.warning(f"Bad partition entry: {entry}")
    return parts


def generate_ini_for_firmware(firmware_path: str, force_cfe: bool = False,
                              ini_path: str = None, backup: bool = True,
                              package_id: str = DEFAULT_PACKAGE_ID,
                              product_id: str = DEFAULT_PRODUCT_ID,
                              partitions: str = None) -> str:
    """Stworz .ini obok firmware'u. Zwraca path."""
    filename = os.path.basename(firmware_path)
    folder = os.path.dirname(firmware_path) or '.'
    base = os.path.splitext(filename)[0]
    if ini_path is None:
        ini_path = os.path.join(folder, f"{base}.ini")

    filesize, fw_crc = process_firmware_file(firmware_path)

    if backup and os.path.isfile(ini_path):
        bak = ini_path + ".bak"
        if not os.path.isfile(bak):
            shutil.copy2(ini_path, bak)
            LOG.info(f"Backup oryginalu: {os.path.basename(bak)}")

    content = generate_ini_content(
        filename, filesize, fw_crc, force_cfe=force_cfe,
        package_id=package_id, product_id=product_id,
        partitions=partitions
    )
    with open(ini_path, 'w', newline='\n', encoding='ascii') as f:
        f.write(content)

    mode = "FORCE-CFE" if force_cfe else "normalny"
    LOG.info(f"INI [{mode}]: {ini_path}")
    LOG.info(f"  Size: {filesize:,} bytes, CRC32: 0x{fw_crc:08X}")
    return ini_path


# ============================================================================
# 5. PACKET BUILDER (replika sub_4202F0)
# ============================================================================
def build_packet(opcode: int, chunk_data: bytes, chunk_counter: int,
                 total_size: int, firmware_crc: int,
                 package_id: str, product_id: str) -> bytes:
    """Build 1086-byte MUT packet. Bug B6: bezpiecznie obsluguje non-ASCII."""
    if opcode == OPCODE_DATA:
        ctrl = CTRL_DATA
    elif opcode == OPCODE_LAST:
        ctrl = CTRL_LAST
    elif opcode == OPCODE_INIT:
        ctrl = CTRL_INIT
    else:
        raise ValueError(f"Bad opcode: {opcode}")

    # Pad chunk_data to 1024 bytes
    if len(chunk_data) > CHUNK_SIZE:
        chunk_data = chunk_data[:CHUNK_SIZE]
    elif len(chunk_data) < CHUNK_SIZE:
        chunk_data = chunk_data + b'\x00' * (CHUNK_SIZE - len(chunk_data))

    # CRC32 of (padded) chunk
    chunk_crc = crc32(chunk_data)

    # PACKAGE_ID/PRODUCT_ID - safe encode (Bug B6: ignore non-ASCII chars)
    pkg = (package_id or "").encode('ascii', errors='ignore')[:20].ljust(20, b'\x00')
    prd = (product_id or "").encode('ascii', errors='ignore')[:20].ljust(20, b'\x00')

    # Header (62 bytes):
    # 0-3:   ctrl (LE u32)
    # 4-7:   chunk_counter (LE u32)
    # 8-11:  chunk_crc (LE u32)
    # 12-15: total_size (LE u32)
    # 16-19: firmware_crc (LE u32)
    # 20-39: PACKAGE_ID (20 bytes)
    # 40-41: unknown_word (2 bytes, default 00 00)
    # 42-61: PRODUCT_ID (20 bytes)
    header = struct.pack(
        '<IIIII20sH20s',
        ctrl, chunk_counter, chunk_crc, total_size, firmware_crc,
        pkg, 0x0000, prd
    )

    return header + chunk_data


def build_init_payload(partitions: List[dict]) -> bytes:
    """Build INIT packet partition table (32 bytes per partition)."""
    payload = b''
    for p in partitions:
        name = p['name'].encode('ascii')[:20].ljust(20, b'\x00')
        flag_byte = 0x02 if p.get('cover', p.get('flag') == 'cover') else 0x01
        entry = struct.pack('<20sIIB3s', name, p['start'], p['end'],
                             flag_byte, b'\x00\x00\x00')
        payload += entry
    return payload


# ============================================================================
# 6. NETWORK ADAPTER HELPERS
# ============================================================================
@dataclass
class NetworkAdapter:
    name: str
    ip: str
    is_wifi: bool = False
    is_virtual: bool = False
    is_loopback: bool = False
    status: str = "Unknown"
    link_speed: str = ""
    mac: str = ""

    def __str__(self):
        return f"{self.ip:18s} {self.name}"


def list_network_adapters() -> List[NetworkAdapter]:
    """Lista kart sieciowych Windows z IPv4."""
    adapters = []
    try:
        result = subprocess.run(
            ['ipconfig', '/all'],
            capture_output=True, text=True, encoding='cp852', errors='replace',
            timeout=10
        )
        current_name = None
        current_mac = ""
        for raw_line in result.stdout.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            # Header: "Karta Ethernet:" / "Wireless LAN adapter Wi-Fi:"
            if line and not line.startswith(' ') and not line.startswith('\t') \
                    and line.rstrip().endswith(':'):
                current_name = line.strip().rstrip(':').strip()
                current_mac = ""
                continue
            # MAC
            if 'Physical Address' in line or 'Adres fizyczny' in line:
                if ':' in line:
                    current_mac = line.split(':', 1)[1].strip().replace('-', ':').upper()
                continue
            # IPv4
            if 'IPv4' in line and ':' in line:
                ip = line.split(':', 1)[1].strip()
                ip = ip.replace('(Preferred)', '').replace('(Preferowane)', '').strip()
                if ip and current_name and not ip.startswith('169.254.'):
                    name_lower = current_name.lower()
                    is_wifi = any(w in name_lower for w in [
                        'wireless', 'wi-fi', 'wifi', 'bezprzewod'])
                    is_virtual = any(w in name_lower for w in [
                        'vmware', 'hyper-v', 'virtualbox', 'tap', 'tailscale',
                        'wireguard', 'openvpn', 'pseudo', 'bluetooth'])
                    is_loopback = ip.startswith('127.')
                    adapters.append(NetworkAdapter(
                        name=current_name, ip=ip,
                        is_wifi=is_wifi, is_virtual=is_virtual,
                        is_loopback=is_loopback, mac=current_mac
                    ))
    except Exception as e:
        LOG.warning(f"ipconfig failed: {e}")

    if not adapters:
        try:
            _, _, ips = socket.gethostbyname_ex(socket.gethostname())
            for ip in ips:
                if not ip.startswith('127.') and not ip.startswith('169.254.'):
                    adapters.append(NetworkAdapter(
                        name='host', ip=ip, status='Up'))
        except Exception:
            pass

    # Annotate status (Up/Down)
    try:
        ps_result = subprocess.run([
            'powershell', '-NoProfile', '-Command',
            'Get-NetAdapter | Select-Object Name,Status,LinkSpeed | ConvertTo-Json'
        ], capture_output=True, text=True, timeout=10)
        if ps_result.returncode == 0 and ps_result.stdout.strip():
            data = json.loads(ps_result.stdout)
            if isinstance(data, dict):
                data = [data]
            ps_map = {d['Name']: d for d in data}
            for a in adapters:
                if a.name in ps_map:
                    a.status = ps_map[a.name].get('Status', 'Unknown')
                    a.link_speed = ps_map[a.name].get('LinkSpeed', '')
    except Exception as e:
        LOG.debug(f"PS Get-NetAdapter failed: {e}")

    return adapters


def adapter_for_ip(ip: str) -> Optional[NetworkAdapter]:
    """Zwraca info o adapterze dla IP, lub None."""
    for a in list_network_adapters():
        if a.ip == ip:
            return a
    return None


def auto_detect_pc_ip(prefer_subnet: str = '192.168.1.') -> Optional[str]:
    """Znajdz najlepszy IP karty (NIE WiFi!)."""
    adapters = list_network_adapters()
    # 1. Wired (NIE WiFi, NIE virtual) z preferowana subnet
    for a in adapters:
        if a.ip.startswith(prefer_subnet) and not a.is_wifi and not a.is_virtual:
            return a.ip
    # 2. Wired z 192.168.x.x
    for a in adapters:
        if a.ip.startswith('192.168.') and not a.is_wifi and not a.is_virtual:
            return a.ip
    # 3. Wired cokolwiek
    for a in adapters:
        if not a.is_wifi and not a.is_virtual and not a.is_loopback:
            return a.ip
    return None


# Cache for router_is_alive (bug B2: nie blokowac GUI)
_PING_CACHE: Dict[str, Tuple[float, bool]] = {}


def router_is_alive(ip: str = '192.168.1.1', timeout_ms: int = 1000,
                    use_cache: bool = True) -> bool:
    """Ping router. True = router odpowiada. Cached aby nie blokowac GUI."""
    if use_cache and ip in _PING_CACHE:
        ts, val = _PING_CACHE[ip]
        if time.time() - ts < ROUTER_PING_CACHE_SEC:
            return val
    try:
        result = subprocess.run(
            ['ping', '-n', '1', '-w', str(timeout_ms), ip],
            capture_output=True, text=True, timeout=timeout_ms / 1000.0 + 2
        )
        alive = result.returncode == 0 and ('TTL=' in result.stdout or 'ttl=' in result.stdout)
    except Exception:
        alive = False
    _PING_CACHE[ip] = (time.time(), alive)
    return alive


def router_ping_async(ip: str, callback: Callable[[bool], None]):
    """Ping w osobnym wątku - wynik przez callback (NIE blokuje GUI)."""
    def _worker():
        result = router_is_alive(ip, use_cache=False)
        try:
            callback(result)
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


def is_admin() -> bool:
    """Czy proces jest Administrator (Windows)."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Restartuj skrypt z UAC. Zwraca False jezeli juz admin."""
    if is_admin():
        return False
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            f'"{os.path.abspath(__file__)}" {" ".join(sys.argv[1:])}',
            None, 1
        )
        return True
    except Exception as e:
        LOG.error(f"UAC relaunch failed: {e}")
        return False


# ============================================================================
# 7. SAFETY CHECKER
# ============================================================================
@dataclass
class SafetyCheck:
    name: str
    description: str
    status: str = "PENDING"             # PENDING / PASS / WARN / FAIL
    message: str = ""
    blocking: bool = True
    fixable: bool = False
    fix_action: Optional[Callable] = None


class SafetyChecker:
    """Pre-flight + runtime safety checks."""

    def __init__(self, firmware_path: str = "", ini_path: str = "",
                 pc_ip: str = "", model: ModelPreset = None,
                 expert_mode: bool = False):
        self.firmware_path = firmware_path
        self.ini_path = ini_path
        self.pc_ip = pc_ip
        self.model = model or MODELS["Custom (manual config)"]
        self.expert_mode = expert_mode
        self.checks: List[SafetyCheck] = []

    def run_all(self) -> List[SafetyCheck]:
        """Uruchom wszystkie checki. Zwraca liste (tez updated self.checks)."""
        self.checks = []
        self._check_admin()
        self._check_python()
        self._check_firmware_file()
        self._check_firmware_magic()
        self._check_ini_file()
        self._check_ini_valid()
        self._check_ini_crc()
        self._check_adapter_selected()
        self._check_not_wifi()
        self._check_link_up()
        self._check_pc_ip_subnet()
        self._check_router_not_alive()
        self._check_secure_boot_warning()
        return self.checks

    def is_blocking_failure(self) -> bool:
        """Czy jest jakikolwiek blocking failure ktory uniemozliwia start."""
        for c in self.checks:
            if c.status == "FAIL" and c.blocking and not self.expert_mode:
                return True
        return False

    def _add(self, name: str, description: str, status: str, message: str = "",
             blocking: bool = True, fixable: bool = False,
             fix_action: Callable = None):
        self.checks.append(SafetyCheck(
            name=name, description=description, status=status,
            message=message, blocking=blocking, fixable=fixable,
            fix_action=fix_action
        ))

    # --- Individual checks ---
    def _check_admin(self):
        if is_admin():
            self._add("Admin uprawnienia", "Proces uruchomiony jako Admin",
                      "PASS", "OK")
        else:
            self._add("Admin uprawnienia",
                      "Wymagane do bind portu 13456 + zmiana IP karty",
                      "FAIL",
                      "Restart jako Administrator (PowerShell admin)",
                      blocking=True, fixable=True,
                      fix_action=relaunch_as_admin)

    def _check_python(self):
        if sys.version_info >= (3, 7):
            self._add("Python version",
                      f"Python {sys.version_info.major}.{sys.version_info.minor}",
                      "PASS")
        else:
            self._add("Python version", "Wymagane >= 3.7",
                      "FAIL", f"Masz {sys.version}", blocking=True)

    def _check_firmware_file(self):
        if not self.firmware_path:
            self._add("Firmware file", "Plik .bin firmware", "FAIL",
                      "Nie wybrano pliku")
            return
        if not os.path.isfile(self.firmware_path):
            self._add("Firmware file", "", "FAIL",
                      f"Plik nie istnieje: {self.firmware_path}")
            return
        size = os.path.getsize(self.firmware_path)
        if size < 1024 * 1024:
            self._add("Firmware file", "", "WARN",
                      f"Plik tylko {size} bytes - prawdopodobnie uszkodzony",
                      blocking=False)
        else:
            self._add("Firmware file", f"{size:,} bytes", "PASS")

    def _check_firmware_magic(self):
        if not self.firmware_path or not os.path.isfile(self.firmware_path):
            return
        ok, magic = check_firmware_magic(self.firmware_path)
        if ok:
            self._add("Firmware magic",
                      "Huawei magic 0x1AF00F1A na offset 0x4",
                      "PASS")
        else:
            self._add("Firmware magic",
                      "Magic NIE pasuje - to NIE Huawei firmware?",
                      "WARN",
                      f"Magic={magic.hex()} (oczekiwane: 1af00f1a)",
                      blocking=False)

    def _check_ini_file(self):
        if not self.ini_path:
            if self.firmware_path:
                self.ini_path = str(Path(self.firmware_path).with_suffix('.ini'))
        if self.ini_path and os.path.isfile(self.ini_path):
            self._add("INI file", f"{os.path.basename(self.ini_path)}", "PASS")
        else:
            self._add("INI file", "Brak INI - kliknij Generate INI",
                      "FAIL", "INI nie istnieje", blocking=True, fixable=True)

    def _check_ini_valid(self):
        if not self.ini_path or not os.path.isfile(self.ini_path):
            return
        try:
            fields = parse_ini(self.ini_path)
        except Exception as e:
            self._add("INI valid", f"INI parse error: {e}", "FAIL", "")
            return
        required = ['IMAGE_NAME', 'IMAGE_SIZE', 'FIRMWARE_CRC_SUM',
                    'INI_CRC_SUM', 'PARTITIONS']
        missing = [k for k in required if k not in fields]
        if missing:
            self._add("INI valid",
                      f"Brakujace pola: {', '.join(missing)}",
                      "FAIL", "Regenerate INI")
            return
        # Bug B7: empty partitions list
        partitions = parse_partitions(fields.get('PARTITIONS', ''))
        if not partitions:
            self._add("INI valid",
                      "PARTITIONS=... jest puste lub format zly",
                      "FAIL", "Regenerate INI")
            return
        # Bug B9: IMAGE_NAME zgodne z faktyczna nazwa
        if self.firmware_path:
            real_name = os.path.basename(self.firmware_path)
            ini_name = fields.get('IMAGE_NAME', '')
            if ini_name != real_name:
                self._add("INI valid",
                          f"IMAGE_NAME='{ini_name}' != faktyczna nazwa '{real_name}'",
                          "WARN",
                          "Router moze odrzucic - zregeneruj INI",
                          blocking=False)
                return
        self._add("INI valid", f"Wszystkie pola OK ({len(partitions)} partycji)", "PASS")

    def _check_ini_crc(self):
        if not self.ini_path or not os.path.isfile(self.ini_path):
            return
        if not self.firmware_path or not os.path.isfile(self.firmware_path):
            return
        try:
            fields = parse_ini(self.ini_path)
            ini_fw_crc = int(fields.get('FIRMWARE_CRC_SUM', '0'))
            real_size, real_crc = process_firmware_file(self.firmware_path)
            if ini_fw_crc == real_crc:
                self._add("Firmware CRC32",
                          f"INI={ini_fw_crc} == real={real_crc}", "PASS")
            else:
                self._add("Firmware CRC32",
                          f"INI={ini_fw_crc} != real={real_crc} (regenerate INI!)",
                          "FAIL", "", blocking=True, fixable=True)
        except Exception as e:
            self._add("Firmware CRC32", f"CRC check error: {e}", "WARN",
                      blocking=False)

    def _check_adapter_selected(self):
        if not self.pc_ip:
            self._add("Karta sieciowa", "Brak wybranej karty", "FAIL",
                      "Wybierz adapter w GUI")
            return
        adapter = adapter_for_ip(self.pc_ip)
        if adapter:
            self._add("Karta sieciowa", f"{adapter.name} ({adapter.ip})", "PASS")
        else:
            self._add("Karta sieciowa",
                      f"IP {self.pc_ip} NIE istnieje na zadnej karcie!",
                      "FAIL", "Ustaw IP w Windows: New-NetIPAddress")

    def _check_not_wifi(self):
        if not self.pc_ip:
            return
        adapter = adapter_for_ip(self.pc_ip)
        if not adapter:
            return
        if adapter.is_wifi:
            self._add("Typ karty (NIE WiFi)",
                      f"WYBRANA WiFi: {adapter.name}",
                      "FAIL",
                      "WiFi multicast = pakiety pojda do INNEJ sieci. Uzyj Ethernet!",
                      blocking=True)
        elif adapter.is_virtual:
            self._add("Typ karty (NIE WiFi)",
                      f"Karta WIRTUALNA: {adapter.name}",
                      "WARN", "Virtual adapter - upewnij sie ze to dobry wybor",
                      blocking=False)
        else:
            self._add("Typ karty (NIE WiFi)",
                      f"Wired Ethernet: {adapter.name}", "PASS")

    def _check_link_up(self):
        if not self.pc_ip:
            return
        adapter = adapter_for_ip(self.pc_ip)
        if not adapter:
            return
        if adapter.status == "Up":
            self._add("Link UP", f"Status={adapter.status}, speed={adapter.link_speed}",
                      "PASS")
        elif adapter.status == "Disconnected":
            self._add("Link UP", f"Status={adapter.status} - kabel odpiety",
                      "FAIL", "Podlacz kabel Ethernet do routera",
                      blocking=True)
        else:
            self._add("Link UP", f"Status={adapter.status}", "WARN",
                      blocking=False)

    def _check_pc_ip_subnet(self):
        if not self.pc_ip or not self.model:
            return
        try:
            net = ipaddress.ip_network(
                f"{self.model.router_ip}/{self.model.subnet_prefix}",
                strict=False
            )
            if ipaddress.ip_address(self.pc_ip) in net:
                self._add("PC IP w subnet routera",
                          f"{self.pc_ip} ∈ {net}", "PASS")
            else:
                self._add("PC IP w subnet routera",
                          f"{self.pc_ip} NIE jest w {net} (router={self.model.router_ip})",
                          "WARN",
                          f"Zalecane: pc_ip = {self.model.pc_ip}",
                          blocking=False, fixable=True)
        except Exception as e:
            self._add("PC IP w subnet routera", f"Subnet check error: {e}",
                      "WARN", blocking=False)

    def _check_router_not_alive(self):
        if not self.model:
            return
        # Cached ping (NIE blokuje GUI dluzej niz 3s)
        if router_is_alive(self.model.router_ip, timeout_ms=300, use_cache=True):
            self._add("Router NIE odpowiada (powinien byc cegla)",
                      f"{self.model.router_ip} ODPOWIADA na ping!",
                      "FAIL",
                      "To znaczy ze router DZIALA NORMALNIE (nie cegla) "
                      "lub jestes podpiety do INNEGO routera. "
                      "Cegla w upgrade mode NIE odpowiada na ping.",
                      blocking=True)
        else:
            self._add("Router NIE odpowiada (powinien byc cegla)",
                      f"{self.model.router_ip} nie odpowiada (OK - probably brick)",
                      "PASS")

    def _check_secure_boot_warning(self):
        if not self.model:
            return
        if self.model.secure_boot:
            self._add("Secure boot warning",
                      f"{self.model.name} ma secure boot w silicon",
                      "WARN",
                      "Software recovery TEGO modelu jest NIEMOZLIWA. "
                      "Tool wysle pakiety, ale router odrzuci firmware. "
                      "Patrz _research/FINAL_REPORT.md.",
                      blocking=False)
        else:
            self._add("Secure boot warning",
                      f"{self.model.name} - bootloader bez secure boot",
                      "PASS")


# ============================================================================
# 8. NETWORK MANAGER (set IP, backup, restore)
# ============================================================================
class NetworkManager:
    """Backup + set static IP + restore DHCP via PowerShell."""

    BACKUP_FILE = Path.cwd() / "_unbrick_network_backup.json"
    DISABLED_FILE = Path.cwd() / "_unbrick_disabled_adapters.json"

    def __init__(self):
        self.backed_up = False
        self.disabled_adapters: List[str] = []
        # Load tracked disabled adapters jezeli istnieje
        if self.DISABLED_FILE.exists():
            try:
                self.disabled_adapters = json.loads(self.DISABLED_FILE.read_text(encoding='utf-8'))
            except Exception:
                self.disabled_adapters = []

    def backup_state(self, force: bool = False) -> dict:
        """Zapisz stan sieci (wszystkie adaptery)."""
        state = {
            'timestamp': datetime.datetime.now().isoformat(),
            'adapters': []
        }
        try:
            ps = (
                "Get-NetAdapter | ForEach-Object { "
                "  $name = $_.Name; "
                "  $cfg = Get-NetIPConfiguration -InterfaceAlias $name -EA SilentlyContinue; "
                "  $ip = $cfg.IPv4Address | Select -First 1; "
                "  $dhcp = (Get-NetIPInterface -InterfaceAlias $name -AddressFamily IPv4 -EA SilentlyContinue).Dhcp; "
                "  $dns = (Get-DnsClientServerAddress -InterfaceAlias $name -AddressFamily IPv4 -EA SilentlyContinue).ServerAddresses; "
                "  [PSCustomObject]@{ "
                "    Name=$name; Status=\"$($_.Status)\"; "
                "    IPv4=$ip.IPAddress; Prefix=$ip.PrefixLength; "
                "    Gateway=($cfg.IPv4DefaultGateway | Select -First 1).NextHop; "
                "    Dhcp=\"$dhcp\"; Dns=$dns "
                "  } "
                "} | ConvertTo-Json -Depth 5"
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]
                state['adapters'] = data
        except Exception as e:
            LOG.error(f"Network backup failed: {e}")

        # Bug B4: nie nadpisuj jak juz istnieje (zachowaj original DHCP state)
        if self.BACKUP_FILE.exists() and not force:
            LOG.info(f"Network backup juz istnieje: {self.BACKUP_FILE} (uzyj force=True aby nadpisac)")
            try:
                return json.loads(self.BACKUP_FILE.read_text(encoding='utf-8'))
            except Exception:
                pass

        with open(self.BACKUP_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, default=str)
        self.backed_up = True
        LOG.info(f"Network backup: {self.BACKUP_FILE}")
        return state

    def set_static_ip(self, interface: str, ip: str, prefix: int = 24) -> bool:
        """Ustaw static IP na karcie."""
        try:
            ps = (
                f"Set-NetIPInterface -InterfaceAlias '{interface}' -Dhcp Disabled -EA Stop; "
                f"Get-NetIPAddress -InterfaceAlias '{interface}' -AddressFamily IPv4 -EA SilentlyContinue "
                f"  | Remove-NetIPAddress -Confirm:$false -EA SilentlyContinue; "
                f"New-NetIPAddress -InterfaceAlias '{interface}' -IPAddress '{ip}' -PrefixLength {prefix} -EA Stop"
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                LOG.info(f"Static IP {ip}/{prefix} set on {interface}")
                return True
            else:
                LOG.error(f"set_static_ip failed: {result.stderr}")
                return False
        except Exception as e:
            LOG.error(f"set_static_ip exception: {e}")
            return False

    def restore_dhcp(self, interface: str) -> bool:
        """Przywroc DHCP na karcie."""
        try:
            ps = (
                f"Get-NetIPAddress -InterfaceAlias '{interface}' -AddressFamily IPv4 -EA SilentlyContinue "
                f"  | Remove-NetIPAddress -Confirm:$false -EA SilentlyContinue; "
                f"Set-NetIPInterface -InterfaceAlias '{interface}' -Dhcp Enabled -EA SilentlyContinue; "
                f"Set-DnsClientServerAddress -InterfaceAlias '{interface}' -ResetServerAddresses -EA SilentlyContinue"
            )
            subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=10)
            LOG.info(f"DHCP restored on {interface}")
            return True
        except Exception as e:
            LOG.error(f"restore_dhcp exception: {e}")
            return False

    def add_firewall_rules(self) -> bool:
        """Dodaj reguly firewall dla UDP 13456 in/out."""
        try:
            ps = (
                "if (-not (Get-NetFirewallRule -DisplayName 'HuaweiMUT-UDP13456-In' -EA SilentlyContinue)) { "
                "  New-NetFirewallRule -DisplayName 'HuaweiMUT-UDP13456-In' -Direction Inbound "
                "    -Protocol UDP -LocalPort 13456 -Action Allow -Profile Any | Out-Null }; "
                "if (-not (Get-NetFirewallRule -DisplayName 'HuaweiMUT-UDP13456-Out' -EA SilentlyContinue)) { "
                "  New-NetFirewallRule -DisplayName 'HuaweiMUT-UDP13456-Out' -Direction Outbound "
                "    -Protocol UDP -LocalPort 13456 -Action Allow -Profile Any | Out-Null }"
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            LOG.error(f"Firewall rules add failed: {e}")
            return False

    def disable_other_adapters(self, keep_alive: str) -> List[str]:
        """Wylacz inne karty (Wi-Fi, Tailscale, etc) zeby multicast szedl tylko Ethernet."""
        disabled = []
        for adapter_name in ADAPTERS_TO_DISABLE:
            if adapter_name == keep_alive:
                continue
            try:
                ps = (
                    f"$a = Get-NetAdapter -Name '{adapter_name}' -EA SilentlyContinue; "
                    f"if ($a -and $a.Status -ne 'Disabled') {{ "
                    f"  Disable-NetAdapter -Name '{adapter_name}' -Confirm:$false -EA Stop; "
                    f"  Write-Output 'disabled' "
                    f"}}"
                )
                result = subprocess.run(
                    ['powershell', '-NoProfile', '-Command', ps],
                    capture_output=True, text=True, timeout=10
                )
                if 'disabled' in result.stdout.lower():
                    disabled.append(adapter_name)
                    LOG.info(f"Disabled adapter: {adapter_name}")
            except Exception as e:
                LOG.debug(f"Could not disable {adapter_name}: {e}")
        # Save disabled list for later restore
        self.disabled_adapters = disabled
        try:
            self.DISABLED_FILE.write_text(json.dumps(disabled), encoding='utf-8')
        except Exception:
            pass
        return disabled

    def enable_disabled_adapters(self) -> int:
        """Re-enable adapters zostale wylaczone przez disable_other_adapters."""
        if not self.disabled_adapters:
            return 0
        count = 0
        for adapter_name in self.disabled_adapters:
            try:
                ps = (
                    f"$a = Get-NetAdapter -Name '{adapter_name}' -EA SilentlyContinue; "
                    f"if ($a -and $a.Status -eq 'Disabled') {{ "
                    f"  Enable-NetAdapter -Name '{adapter_name}' -Confirm:$false -EA Stop; "
                    f"  Write-Output 'enabled' "
                    f"}}"
                )
                result = subprocess.run(
                    ['powershell', '-NoProfile', '-Command', ps],
                    capture_output=True, text=True, timeout=10
                )
                if 'enabled' in result.stdout.lower():
                    count += 1
                    LOG.info(f"Re-enabled adapter: {adapter_name}")
            except Exception as e:
                LOG.debug(f"Could not enable {adapter_name}: {e}")
        self.disabled_adapters = []
        try:
            if self.DISABLED_FILE.exists():
                self.DISABLED_FILE.unlink()
        except Exception:
            pass
        return count

    def set_speed_duplex_100m_full(self, interface: str) -> bool:
        """Set 100Mbps Full Duplex (lepszy dla multicast - z _flash_prepare.ps1)."""
        try:
            ps = (
                f"$sp = Get-NetAdapterAdvancedProperty -Name '{interface}' -EA SilentlyContinue "
                f"  | Where-Object {{ $_.DisplayName -match 'Speed.*Duplex|Speed.*and.*Duplex|Predkosc' }} "
                f"  | Select-Object -First 1; "
                f"if ($sp) {{ "
                f"  $tgt = $sp.ValidDisplayValues | Where-Object {{ $_ -match '100\\s*Mbps.*Full|100.*Pelny' }} | Select-Object -First 1; "
                f"  if ($tgt -and $sp.DisplayValue -ne $tgt) {{ "
                f"    Set-NetAdapterAdvancedProperty -Name '{interface}' -DisplayName $sp.DisplayName -DisplayValue $tgt; "
                f"    Write-Output 'set' "
                f"  }} "
                f"}}"
            )
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps],
                capture_output=True, text=True, timeout=10
            )
            return 'set' in result.stdout.lower()
        except Exception as e:
            LOG.debug(f"set_speed_duplex_100m_full: {e}")
            return False

    def telnet_diag_restore_default(self, router_ip: str = DEFAULT_ROUTER_IP_AFTER_FLASH) -> bool:
        """Wyslij 'diag restore default' przez telnet (post-flash, Guide.txt krok 13)."""
        try:
            # Test ping najpierw
            if not router_is_alive(router_ip, timeout_ms=2000, use_cache=False):
                LOG.warning(f"Router {router_ip} nie odpowiada na ping - czy debug fw boot'uje?")
                return False
            # Uzyj telnetlib lub wywolaj telnet.exe
            try:
                import telnetlib
                tn = telnetlib.Telnet(router_ip, 23, timeout=10)
                time.sleep(1)
                tn.write(b"diag restore default\r\n")
                time.sleep(5)
                tn.close()
                LOG.info(f"Telnet 'diag restore default' wyslano do {router_ip}")
                return True
            except ImportError:
                # Python 3.13+ usuwa telnetlib - uzyj subprocess telnet.exe
                LOG.info("telnetlib niedostepny - uruchamiam telnet.exe interaktywnie")
                subprocess.Popen([
                    'cmd', '/k',
                    f'title TELNET {router_ip} - wpisz: diag restore default && telnet {router_ip}'
                ], creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
                return True
        except Exception as e:
            LOG.error(f"Telnet failed: {e}")
            return False

    def open_telnet_window(self, router_ip: str = DEFAULT_ROUTER_IP_AFTER_FLASH) -> bool:
        """Otworz interaktywne okno cmd z telnet'em (user wpisuje 'diag restore default')."""
        try:
            subprocess.Popen([
                'cmd', '/k',
                f'title TELNET {router_ip} - wpisz: diag restore default && telnet {router_ip}'
            ], creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
            return True
        except Exception as e:
            LOG.error(f"Open telnet window: {e}")
            return False

    def renew_dhcp(self) -> bool:
        """Wymus DHCP renew (ipconfig /renew)."""
        try:
            subprocess.run(['ipconfig', '/renew'],
                           capture_output=True, text=True, timeout=15)
            return True
        except Exception:
            return False


# ============================================================================
# 9. MUT ENGINE (send loop, threading)
# ============================================================================
@dataclass
class MutStats:
    passes_completed: int = 0
    packets_sent: int = 0
    bytes_sent: int = 0
    errors: int = 0
    start_time: float = 0
    last_packet_time: float = 0
    responses_received: List[Tuple[float, str, bytes]] = field(default_factory=list)


class MutEngine:
    """Multicast send engine - threaded, stoppable."""

    def __init__(self, firmware_path: str, ini_path: str,
                 pc_ip: str, dest_ip: str = MULTICAST_IP,
                 port: int = MULTICAST_PORT, interval_ms: int = DEFAULT_INTERVAL_MS,
                 ttl: int = DEFAULT_TTL, max_passes: int = MAX_PASSES_DEFAULT,
                 use_multicast: bool = True, listen: bool = False,
                 progress_callback: Callable = None,
                 log_callback: Callable = None):
        self.firmware_path = firmware_path
        self.ini_path = ini_path
        self.pc_ip = pc_ip
        self.dest_ip = dest_ip
        self.port = port
        self.interval_ms = interval_ms
        self.ttl = ttl
        self.max_passes = max_passes
        self.use_multicast = use_multicast
        self.listen = listen
        self.progress_callback = progress_callback or (lambda **kw: None)
        self.log_callback = log_callback or (lambda msg, level='INFO': None)

        # Parse INI
        self.ini_fields = parse_ini(ini_path)
        self.package_id = self.ini_fields.get('PACKAGE_ID', DEFAULT_PACKAGE_ID)
        self.product_id = self.ini_fields.get('PRODUCT_ID', DEFAULT_PRODUCT_ID)
        self.partitions = parse_partitions(
            self.ini_fields.get('PARTITIONS', PARTITIONS_NORMAL)
        )

        # Firmware info
        self.file_size, self.firmware_crc = process_firmware_file(firmware_path)

        # State
        self.stats = MutStats()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._listen_thread: Optional[threading.Thread] = None

    def setup_socket(self) -> socket.socket:
        """Replika sub_41F0A0 z fallback dla WinError 10049."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        try:
            s.bind((self.pc_ip, self.port))
        except OSError as e:
            self.log_callback(f"Bind {self.pc_ip}:{self.port} failed: {e} - retry 0.0.0.0",
                              "WARN")
            s.bind(('0.0.0.0', self.port))

        if self.use_multicast:
            try:
                mreq = socket.inet_aton(self.dest_ip) + socket.inet_aton(self.pc_ip)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError as e:
                self.log_callback(f"IP_ADD_MEMBERSHIP failed: {e}", "WARN")
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.ttl)
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                             socket.inet_aton(self.pc_ip))
            except OSError as e:
                self.log_callback(f"IP_MULTICAST_IF failed: {e}", "WARN")

        return s

    def start(self):
        """Uruchom send loop w osobnym watku."""
        if self.running:
            return
        self.running = True
        self.stats.start_time = time.time()
        self.thread = threading.Thread(target=self._send_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Zatrzymaj send loop."""
        self.running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def _send_loop(self):
        """Main send loop (in thread)."""
        try:
            self._sock = self.setup_socket()
            dest = (self.dest_ip, self.port)

            if self.listen:
                self._listen_thread = threading.Thread(
                    target=self._listen_loop, args=(self._sock,), daemon=True
                )
                self._listen_thread.start()

            self.log_callback(
                f"Send loop start: {self.firmware_path} -> {dest}, interval={self.interval_ms}ms",
                "INFO"
            )

            while self.running:
                if self.max_passes and self.stats.passes_completed >= self.max_passes:
                    self.log_callback(
                        f"Max passes ({self.max_passes}) reached, stopping", "INFO"
                    )
                    break
                self._send_one_pass(self._sock, dest)
                self.stats.passes_completed += 1
                self.progress_callback(
                    pass_num=self.stats.passes_completed,
                    packets=self.stats.packets_sent,
                    bytes_sent=self.stats.bytes_sent
                )
                # Inter-pass pause
                precise_sleep(self.interval_ms * 2)
        except Exception as e:
            self.log_callback(f"Send loop exception: {e}", "ERROR")
            LOG.exception("Send loop crashed")
        finally:
            self.running = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass

    def _send_one_pass(self, sock: socket.socket, dest: Tuple[str, int]):
        """Single pass: INIT + DATA*N + LAST."""
        chunk_counter = 0

        # 1. INIT packet
        init_payload = build_init_payload(self.partitions)
        init_packet = build_packet(
            opcode=OPCODE_INIT, chunk_data=init_payload,
            chunk_counter=chunk_counter, total_size=self.file_size,
            firmware_crc=self.firmware_crc,
            package_id=self.package_id, product_id=self.product_id
        )
        self._send_packet(sock, init_packet, dest, 'INIT', chunk_counter, 0)
        chunk_counter += 1
        precise_sleep(self.interval_ms)
        if not self.running:
            return

        # 2. DATA + LAST packets
        with open(self.firmware_path, 'rb') as f:
            offset = 0
            while offset < self.file_size and self.running:
                chunk = f.read(CHUNK_SIZE)
                is_last = (offset + len(chunk)) >= self.file_size
                opcode = OPCODE_LAST if is_last else OPCODE_DATA
                packet = build_packet(
                    opcode=opcode, chunk_data=chunk,
                    chunk_counter=chunk_counter, total_size=self.file_size,
                    firmware_crc=self.firmware_crc,
                    package_id=self.package_id, product_id=self.product_id
                )
                self._send_packet(sock, packet, dest,
                                  'LAST' if is_last else 'DATA',
                                  chunk_counter, offset)
                chunk_counter += 1
                offset += len(chunk)
                precise_sleep(self.interval_ms)

    def _send_packet(self, sock, packet, dest, label, seq, offset):
        try:
            sock.sendto(packet, dest)
            self.stats.packets_sent += 1
            self.stats.bytes_sent += len(packet)
            self.stats.last_packet_time = time.time()
            if self.stats.packets_sent % 100 == 0:
                pct = (offset * 100.0 / max(self.file_size, 1))
                self.progress_callback(
                    pass_num=self.stats.passes_completed,
                    packets=self.stats.packets_sent,
                    bytes_sent=self.stats.bytes_sent,
                    offset=offset, total=self.file_size, pct=pct
                )
        except OSError as e:
            self.stats.errors += 1
            self.log_callback(f"sendto failed: {e}", "ERROR")
            self.running = False

    def _listen_loop(self, sock):
        """Sluchaj odpowiedzi od routera. UWAGA: uzywa select() zeby NIE psuc send'a (bug B1)."""
        import select
        while self.running:
            try:
                # select() - non-blocking poll, NIE settimeout (psulo by sendto)
                ready, _, _ = select.select([sock], [], [], 0.5)
                if not ready:
                    continue
                data, addr = sock.recvfrom(4096)
                if addr[0] != self.pc_ip:  # Pomijaj loopback wlasnych
                    self.stats.responses_received.append(
                        (time.time(), addr, data)
                    )
                    self.log_callback(
                        f"*** ROUTER RESPONSE *** {addr}: {len(data)}B {data[:32].hex()}",
                        "INFO"
                    )
            except (OSError, ValueError):
                # ValueError jak socket closed mid-select
                break


# ============================================================================
# 10. GUI - Tkinter Main Window
# ============================================================================
COLOR_BG       = "#1e1e2e"
COLOR_FG       = "#cdd6f4"
COLOR_PANEL    = "#313244"
COLOR_ACCENT   = "#89b4fa"
COLOR_OK       = "#a6e3a1"
COLOR_WARN     = "#f9e2af"
COLOR_ERROR    = "#f38ba8"
COLOR_DANGER   = "#eb6f92"
COLOR_DISABLED = "#6c7086"
FONT_BASE      = ("Consolas", 9)
FONT_BOLD      = ("Consolas", 9, "bold")
FONT_HEADER    = ("Consolas", 14, "bold")
FONT_BIG       = ("Consolas", 16, "bold")


class TkLogHandler(logging.Handler):
    """Logging handler ktory pisze do Tkinter Text widget (thread-safe via queue)."""

    def __init__(self, text_widget: tk.Text, max_lines: int = 1000):
        super().__init__()
        self.text_widget = text_widget
        self.max_lines = max_lines
        self.queue: queue.Queue = queue.Queue()
        self.text_widget.after(100, self._poll_queue)

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.queue.put((record.levelname, msg))
        except Exception:
            pass

    def _poll_queue(self):
        try:
            while not self.queue.empty():
                level, msg = self.queue.get_nowait()
                tag = level.lower()
                self.text_widget.configure(state='normal')
                self.text_widget.insert('end', msg + '\n', tag)
                # Trim old lines
                line_count = int(self.text_widget.index('end-1c').split('.')[0])
                if line_count > self.max_lines:
                    self.text_widget.delete('1.0', f'{line_count - self.max_lines}.0')
                self.text_widget.configure(state='disabled')
                self.text_widget.see('end')
        except queue.Empty:
            pass
        finally:
            self.text_widget.after(100, self._poll_queue)


class UnbrickGUI:
    """Glowne okno GUI - Tkinter."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1100x800")
        self.root.configure(bg=COLOR_BG)
        self.root.minsize(900, 700)

        # State
        self.firmware_path = tk.StringVar()
        self.ini_path = tk.StringVar()
        self.selected_model = tk.StringVar(value="WS7200 / AX3 Pro")
        self.selected_adapter_ip = tk.StringVar()
        self.interval_ms = tk.IntVar(value=DEFAULT_INTERVAL_MS)
        self.max_passes = tk.IntVar(value=MAX_PASSES_DEFAULT)
        self.ttl = tk.IntVar(value=DEFAULT_TTL)
        self.use_unicast = tk.BooleanVar(value=False)
        self.unicast_ip = tk.StringVar()
        self.listen_mode = tk.BooleanVar(value=True)
        self.expert_mode = tk.BooleanVar(value=False)
        self.force_cfe = tk.BooleanVar(value=False)

        self.engine: Optional[MutEngine] = None
        self.network_mgr = NetworkManager()
        self.checks: List[SafetyCheck] = []
        self.is_flashing = False

        # Build UI
        self._setup_styles()
        self._build_ui()
        self._refresh_adapters()
        self._refresh_checks()

        # Atexit: restore network
        atexit.register(self._cleanup)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(".", background=COLOR_BG, foreground=COLOR_FG,
                        fieldbackground=COLOR_PANEL, font=FONT_BASE)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_FG)
        style.configure("Panel.TFrame", background=COLOR_PANEL, relief='flat')
        style.configure("Panel.TLabel", background=COLOR_PANEL, foreground=COLOR_FG)
        style.configure("Header.TLabel", background=COLOR_BG, foreground=COLOR_ACCENT,
                        font=FONT_HEADER)
        style.configure("OK.TLabel", foreground=COLOR_OK, background=COLOR_PANEL)
        style.configure("Warn.TLabel", foreground=COLOR_WARN, background=COLOR_PANEL)
        style.configure("Error.TLabel", foreground=COLOR_ERROR, background=COLOR_PANEL)
        style.configure("TButton", padding=6, background=COLOR_ACCENT,
                        foreground=COLOR_BG, font=FONT_BOLD)
        style.map("TButton",
                  background=[("active", "#74c7ec")],
                  foreground=[("active", COLOR_BG)])
        style.configure("Danger.TButton", background=COLOR_DANGER,
                        foreground=COLOR_BG, font=FONT_BIG)
        style.map("Danger.TButton",
                  background=[("active", "#e64553")])
        style.configure("Big.TButton", background=COLOR_OK,
                        foreground=COLOR_BG, font=FONT_BIG, padding=12)
        style.map("Big.TButton",
                  background=[("active", "#94e2d5"), ("disabled", COLOR_DISABLED)])
        style.configure("TCombobox", fieldbackground=COLOR_PANEL,
                        background=COLOR_PANEL, foreground=COLOR_FG)
        style.configure("TCheckbutton", background=COLOR_BG, foreground=COLOR_FG,
                        font=FONT_BASE)
        style.map("TCheckbutton",
                  background=[("active", COLOR_BG)])
        style.configure("TEntry", fieldbackground=COLOR_PANEL, foreground=COLOR_FG)
        style.configure("Horizontal.TProgressbar", background=COLOR_OK,
                        troughcolor=COLOR_PANEL)

    def _build_ui(self):
        # Top header
        header = ttk.Frame(self.root, style="TFrame")
        header.pack(fill='x', padx=10, pady=(10, 5))
        ttk.Label(header, text=f"⚡ {APP_NAME}", style="Header.TLabel").pack(side='left')
        ttk.Label(header, text=f"v{APP_VERSION}",
                  background=COLOR_BG, foreground=COLOR_DISABLED,
                  font=FONT_BASE).pack(side='left', padx=10)
        ttk.Checkbutton(header, text="Expert mode (override safety)",
                        variable=self.expert_mode,
                        command=self._refresh_checks).pack(side='right')

        # Main container - split left (config) / right (status+log)
        main = ttk.Frame(self.root, style="TFrame")
        main.pack(fill='both', expand=True, padx=10, pady=5)

        left = ttk.Frame(main, style="TFrame")
        left.pack(side='left', fill='both', expand=True, padx=(0, 5))
        right = ttk.Frame(main, style="TFrame")
        right.pack(side='right', fill='both', expand=True, padx=(5, 0))

        # === LEFT: configuration panels ===
        self._build_model_panel(left)
        self._build_firmware_panel(left)
        self._build_network_panel(left)
        self._build_settings_panel(left)
        self._build_buttons(left)

        # === RIGHT: status + progress + log ===
        self._build_status_panel(right)
        self._build_progress_panel(right)
        self._build_log_panel(right)

        # Setup log handler
        self.log_handler = TkLogHandler(self.log_text)
        self.log_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)-5s %(message)s',
            datefmt='%H:%M:%S'
        ))
        LOG.addHandler(self.log_handler)
        self.log_text.tag_config('info', foreground=COLOR_FG)
        self.log_text.tag_config('warning', foreground=COLOR_WARN)
        self.log_text.tag_config('error', foreground=COLOR_ERROR)
        self.log_text.tag_config('debug', foreground=COLOR_DISABLED)

    def _make_panel(self, parent, title: str) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(fill='x', pady=5)
        ttk.Label(panel, text=title, style="Panel.TLabel",
                  font=FONT_BOLD, foreground=COLOR_ACCENT).pack(anchor='w', pady=(0, 5))
        return panel

    def _build_model_panel(self, parent):
        panel = self._make_panel(parent, "1. Wybierz model routera")
        cb = ttk.Combobox(panel, textvariable=self.selected_model,
                          values=list(MODELS.keys()), state='readonly', width=40)
        cb.pack(fill='x')
        cb.bind('<<ComboboxSelected>>', self._on_model_changed)

        self.model_info = tk.Text(panel, height=4, bg=COLOR_PANEL, fg=COLOR_FG,
                                  font=FONT_BASE, relief='flat',
                                  wrap='word', state='disabled')
        self.model_info.pack(fill='x', pady=(5, 0))
        self._on_model_changed()

    def _on_model_changed(self, event=None):
        model = MODELS.get(self.selected_model.get())
        if not model:
            return
        info = (
            f"SoC: {model.soc}\n"
            f"Router IP: {model.router_ip}    PC IP: {model.pc_ip}/{model.subnet_prefix}\n"
            f"Tryb upgrade: {model.upgrade_trigger}\n"
            f"Secure boot: {'TAK (recovery niemozliwe!)' if model.secure_boot else 'NIE'}"
        )
        if model.notes:
            info += f"\nUwaga: {model.notes}"
        self.model_info.configure(state='normal')
        self.model_info.delete('1.0', 'end')
        self.model_info.insert('1.0', info)
        if model.secure_boot:
            self.model_info.configure(fg=COLOR_WARN)
        else:
            self.model_info.configure(fg=COLOR_FG)
        self.model_info.configure(state='disabled')
        self._refresh_checks()

    def _build_firmware_panel(self, parent):
        panel = self._make_panel(parent, "2. Plik firmware (.bin) i INI")
        row1 = ttk.Frame(panel, style="Panel.TFrame")
        row1.pack(fill='x')
        ttk.Entry(row1, textvariable=self.firmware_path).pack(
            side='left', fill='x', expand=True, padx=(0, 5))
        ttk.Button(row1, text="Browse...",
                   command=self._browse_firmware).pack(side='right')

        row2 = ttk.Frame(panel, style="Panel.TFrame")
        row2.pack(fill='x', pady=(5, 0))
        ttk.Checkbutton(row2, text="Force CFE cover (recovery cegly)",
                        variable=self.force_cfe).pack(side='left')
        ttk.Button(row2, text="Generate INI",
                   command=self._generate_ini).pack(side='right')

        self.firmware_info = ttk.Label(panel, text="", style="Panel.TLabel",
                                       foreground=COLOR_DISABLED)
        self.firmware_info.pack(anchor='w', pady=(5, 0))

    def _browse_firmware(self):
        path = filedialog.askopenfilename(
            title="Wybierz firmware .bin",
            filetypes=[("Huawei firmware", "*.bin *.gz.bin"), ("All", "*.*")],
            initialdir=os.getcwd()
        )
        if path:
            self.firmware_path.set(path)
            ini = str(Path(path).with_suffix('.ini'))
            # Feature F9: auto-gen INI jezeli nie istnieje
            if not os.path.isfile(ini):
                if messagebox.askyesno(
                        "Brak INI",
                        f"Plik INI '{os.path.basename(ini)}' nie istnieje.\n\n"
                        f"Wygenerowac automatycznie? (zalecane)"):
                    try:
                        model = MODELS.get(self.selected_model.get())
                        ini = generate_ini_for_firmware(
                            path, force_cfe=self.force_cfe.get(),
                            package_id=model.package_id if model else DEFAULT_PACKAGE_ID,
                            product_id=model.product_id if model else DEFAULT_PRODUCT_ID,
                            partitions=model.default_partitions if model and model.default_partitions else None
                        )
                    except Exception as e:
                        messagebox.showerror("INI gen failed", str(e))
            self.ini_path.set(ini)
            self._update_firmware_info()
            self._refresh_checks()

    def _update_firmware_info(self):
        path = self.firmware_path.get()
        if not path or not os.path.isfile(path):
            self.firmware_info.configure(text="")
            return
        size = os.path.getsize(path)
        ok_magic, magic = check_firmware_magic(path)
        text = f"Size: {size:,} bytes ({size/1024/1024:.2f} MB)"
        if ok_magic:
            text += "  |  Magic: OK"
            self.firmware_info.configure(foreground=COLOR_OK)
        else:
            text += f"  |  Magic: WRONG ({magic.hex()})"
            self.firmware_info.configure(foreground=COLOR_WARN)
        self.firmware_info.configure(text=text)

    def _generate_ini(self):
        path = self.firmware_path.get()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Brak firmware", "Najpierw wybierz plik .bin")
            return
        model = MODELS.get(self.selected_model.get())
        try:
            ini = generate_ini_for_firmware(
                path, force_cfe=self.force_cfe.get(),
                package_id=model.package_id if model else DEFAULT_PACKAGE_ID,
                product_id=model.product_id if model else DEFAULT_PRODUCT_ID,
                partitions=model.default_partitions if model and model.default_partitions else None
            )
            self.ini_path.set(ini)
            messagebox.showinfo("INI", f"Wygenerowano: {os.path.basename(ini)}")
            self._refresh_checks()
        except Exception as e:
            messagebox.showerror("INI Error", str(e))

    def _build_network_panel(self, parent):
        panel = self._make_panel(parent, "3. Karta sieciowa")
        row1 = ttk.Frame(panel, style="Panel.TFrame")
        row1.pack(fill='x')
        self.adapter_combo = ttk.Combobox(row1, textvariable=self.selected_adapter_ip,
                                          state='readonly', width=40)
        self.adapter_combo.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.adapter_combo.bind('<<ComboboxSelected>>', lambda e: self._refresh_checks())
        ttk.Button(row1, text="Refresh",
                   command=self._refresh_adapters).pack(side='right')

        row2 = ttk.Frame(panel, style="Panel.TFrame")
        row2.pack(fill='x', pady=(5, 0))
        ttk.Button(row2, text="Auto-detect",
                   command=self._auto_detect_adapter).pack(side='left', padx=(0, 5))
        ttk.Button(row2, text="Set static IP",
                   command=self._set_static_ip).pack(side='left', padx=(0, 5))
        ttk.Button(row2, text="Restore DHCP",
                   command=self._restore_dhcp).pack(side='left', padx=(0, 5))

        row3 = ttk.Frame(panel, style="Panel.TFrame")
        row3.pack(fill='x', pady=(5, 0))
        ttk.Button(row3, text="Disable WiFi/VPN",
                   command=self._disable_other_adapters).pack(side='left', padx=(0, 5))
        ttk.Button(row3, text="Re-enable adapters",
                   command=self._enable_disabled_adapters).pack(side='left', padx=(0, 5))
        ttk.Button(row3, text="Set 100Mbps Full",
                   command=self._set_100mbps).pack(side='left')

    def _refresh_adapters(self):
        adapters = list_network_adapters()
        items = []
        for a in adapters:
            tag = ""
            if a.is_wifi:
                tag = " [WiFi - DANGEROUS]"
            elif a.is_virtual:
                tag = " [virtual]"
            elif a.status != "Up":
                tag = f" [{a.status}]"
            items.append(f"{a.ip:18s} - {a.name}{tag}")
        self.adapter_combo['values'] = items
        if not self.selected_adapter_ip.get() and items:
            # Auto-detect
            auto = auto_detect_pc_ip()
            if auto:
                for itm in items:
                    if itm.startswith(auto):
                        self.selected_adapter_ip.set(itm)
                        break

    def _auto_detect_adapter(self):
        auto = auto_detect_pc_ip()
        if auto:
            for itm in self.adapter_combo['values']:
                if itm.startswith(auto):
                    self.selected_adapter_ip.set(itm)
                    self._refresh_checks()
                    return
        messagebox.showwarning("Auto-detect", "Nie znaleziono karty wired (Ethernet)")

    def _get_selected_pc_ip(self) -> str:
        sel = self.selected_adapter_ip.get()
        if not sel:
            return ""
        return sel.split(' - ')[0].strip()

    def _get_selected_adapter_name(self) -> str:
        sel = self.selected_adapter_ip.get()
        if not sel:
            return ""
        parts = sel.split(' - ', 1)
        if len(parts) < 2:
            return ""
        # Strip [WiFi - DANGEROUS] / [virtual] tags
        name = parts[1]
        for tag in [' [WiFi - DANGEROUS]', ' [virtual]', ' [Up]', ' [Disconnected]']:
            name = name.replace(tag, '')
        return name.strip()

    def _set_static_ip(self):
        if not is_admin():
            messagebox.showerror("Admin needed",
                                  "Zmiana IP wymaga uprawnien Administrator")
            return
        model = MODELS.get(self.selected_model.get())
        if not model:
            return
        adapter_name = self._get_selected_adapter_name()
        if not adapter_name:
            messagebox.showerror("Adapter", "Najpierw wybierz karte")
            return
        if messagebox.askyesno(
                "Set static IP",
                f"Ustawic IP {model.pc_ip}/{model.subnet_prefix} na karcie '{adapter_name}'?\n\n"
                f"Stare ustawienia zostana zapisane do {self.network_mgr.BACKUP_FILE.name}"):
            self.network_mgr.backup_state()
            ok = self.network_mgr.set_static_ip(adapter_name, model.pc_ip,
                                                model.subnet_prefix)
            if ok:
                messagebox.showinfo("OK", f"IP {model.pc_ip} ustawiony")
                time.sleep(1)
                self._refresh_adapters()
                self._refresh_checks()
            else:
                messagebox.showerror("FAIL", "Nie udalo sie ustawic IP - sprawdz log")

    def _restore_dhcp(self):
        if not is_admin():
            messagebox.showerror("Admin needed",
                                  "Restore DHCP wymaga Administrator")
            return
        adapter_name = self._get_selected_adapter_name()
        if not adapter_name:
            return
        self.network_mgr.restore_dhcp(adapter_name)
        time.sleep(1)
        self._refresh_adapters()
        self._refresh_checks()

    def _disable_other_adapters(self):
        """Disable WiFi/Tailscale/VPN przed flashem (Feature F3, _flash_prepare.ps1)."""
        if not is_admin():
            messagebox.showerror("Admin needed", "Disable adapters wymaga Administrator")
            return
        keep = self._get_selected_adapter_name()
        if not keep:
            messagebox.showerror("Adapter", "Najpierw wybierz aktywna karte")
            return
        if messagebox.askyesno(
                "Disable other adapters",
                f"Wylaczyc wszystkie inne karty zeby multicast szedl tylko przez '{keep}'?\n\n"
                f"Wylaczone karty zostana zachowane do auto-restore po flashu."):
            disabled = self.network_mgr.disable_other_adapters(keep)
            messagebox.showinfo(
                "Done",
                f"Wylaczono {len(disabled)} kart: {', '.join(disabled) if disabled else '(nic do wylaczenia)'}"
            )
            self._refresh_adapters()
            self._refresh_checks()

    def _enable_disabled_adapters(self):
        """Re-enable adapters wylaczone wczesniej (Feature F3)."""
        if not is_admin():
            messagebox.showerror("Admin needed", "Enable adapters wymaga Administrator")
            return
        count = self.network_mgr.enable_disabled_adapters()
        messagebox.showinfo("Done", f"Re-enabled {count} adapter(s)")
        self._refresh_adapters()
        self._refresh_checks()

    def _set_100mbps(self):
        """Set 100Mbps Full Duplex (Feature F2, _flash_prepare.ps1)."""
        if not is_admin():
            messagebox.showerror("Admin needed", "Set speed wymaga Administrator")
            return
        adapter_name = self._get_selected_adapter_name()
        if not adapter_name:
            return
        if self.network_mgr.set_speed_duplex_100m_full(adapter_name):
            messagebox.showinfo("OK", "100Mbps Full Duplex ustawiony (zalecane dla multicast)")
        else:
            messagebox.showinfo(
                "Info",
                "Speed/Duplex juz ustawione lub karta nie obsluguje. "
                "Sprawdz ustawienia karty manualnie."
            )

    def _build_settings_panel(self, parent):
        panel = self._make_panel(parent, "4. Ustawienia zaawansowane")
        grid = ttk.Frame(panel, style="Panel.TFrame")
        grid.pack(fill='x')

        ttk.Label(grid, text="Interval (ms):",
                  style="Panel.TLabel").grid(row=0, column=0, sticky='w')
        ttk.Entry(grid, textvariable=self.interval_ms, width=10).grid(
            row=0, column=1, sticky='w', padx=5)

        ttk.Label(grid, text="Max passes:",
                  style="Panel.TLabel").grid(row=0, column=2, sticky='w', padx=(20, 0))
        ttk.Entry(grid, textvariable=self.max_passes, width=10).grid(
            row=0, column=3, sticky='w', padx=5)

        ttk.Label(grid, text="TTL multicast:",
                  style="Panel.TLabel").grid(row=1, column=0, sticky='w', pady=(5, 0))
        ttk.Entry(grid, textvariable=self.ttl, width=10).grid(
            row=1, column=1, sticky='w', padx=5, pady=(5, 0))

        row3 = ttk.Frame(panel, style="Panel.TFrame")
        row3.pack(fill='x', pady=(5, 0))
        ttk.Checkbutton(row3, text="Listen for router responses",
                        variable=self.listen_mode).pack(side='left')

        row4 = ttk.Frame(panel, style="Panel.TFrame")
        row4.pack(fill='x', pady=(5, 0))
        ttk.Checkbutton(row4, text="Unicast (zamiast multicast):",
                        variable=self.use_unicast).pack(side='left')
        ttk.Entry(row4, textvariable=self.unicast_ip, width=20).pack(
            side='left', padx=5)

    def _build_buttons(self, parent):
        panel = ttk.Frame(parent, style="TFrame")
        panel.pack(fill='x', pady=10)
        self.start_btn = ttk.Button(panel, text="▶ START FLASH", style="Big.TButton",
                                    command=self._on_start_flash)
        self.start_btn.pack(fill='x', padx=20, pady=5)

        self.stop_btn = ttk.Button(panel, text="■ STOP", style="Danger.TButton",
                                   command=self._on_stop_flash, state='disabled')
        self.stop_btn.pack(fill='x', padx=20, pady=5)

        # Post-flash + utility buttons (Feature F1)
        utils = ttk.Frame(parent, style="TFrame")
        utils.pack(fill='x', pady=(5, 0))
        ttk.Button(utils, text="📡 Open Telnet (post-flash)",
                   command=self._open_telnet).pack(side='left', padx=(20, 5))
        ttk.Button(utils, text="⚙️ LED states info",
                   command=self._show_led_info).pack(side='left', padx=5)
        ttk.Button(utils, text="ℹ️ About",
                   command=self._show_about).pack(side='right', padx=(5, 20))

    def _build_status_panel(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(fill='x', pady=5)

        header = ttk.Frame(panel, style="Panel.TFrame")
        header.pack(fill='x')
        ttk.Label(header, text="Pre-flight checklist",
                  style="Panel.TLabel", font=FONT_BOLD,
                  foreground=COLOR_ACCENT).pack(side='left')
        ttk.Button(header, text="↻ Re-check",
                   command=self._refresh_checks).pack(side='right')

        self.checks_frame = ttk.Frame(panel, style="Panel.TFrame")
        self.checks_frame.pack(fill='x', pady=(5, 0))

        self.checks_summary = ttk.Label(panel, text="0 / 0 OK",
                                        style="Panel.TLabel",
                                        font=FONT_BOLD)
        self.checks_summary.pack(anchor='w', pady=(5, 0))

    def _refresh_checks(self):
        # Bug: _on_model_changed wywoluje to PRZED _build_status_panel - skip jak nie ma checks_frame
        if not hasattr(self, 'checks_frame'):
            return
        # Run safety checks
        firmware = self.firmware_path.get()
        ini = self.ini_path.get() if self.ini_path.get() else (
            str(Path(firmware).with_suffix('.ini')) if firmware else ""
        )
        pc_ip = self._get_selected_pc_ip()
        model = MODELS.get(self.selected_model.get())

        checker = SafetyChecker(
            firmware_path=firmware, ini_path=ini, pc_ip=pc_ip,
            model=model, expert_mode=self.expert_mode.get()
        )
        self.checks = checker.run_all()

        # Render
        for w in self.checks_frame.winfo_children():
            w.destroy()

        ok_count = 0
        for c in self.checks:
            row = ttk.Frame(self.checks_frame, style="Panel.TFrame")
            row.pack(fill='x', pady=1)
            if c.status == "PASS":
                icon = "✓"
                color = COLOR_OK
                ok_count += 1
            elif c.status == "WARN":
                icon = "!"
                color = COLOR_WARN
            elif c.status == "FAIL":
                icon = "✗"
                color = COLOR_ERROR
            else:
                icon = "?"
                color = COLOR_DISABLED
            ttk.Label(row, text=f"  {icon}", background=COLOR_PANEL,
                      foreground=color, font=FONT_BOLD).pack(side='left')
            text = f" {c.name}"
            if c.message:
                text += f" — {c.message}"
            ttk.Label(row, text=text, background=COLOR_PANEL,
                      foreground=color, font=FONT_BASE).pack(
                side='left', fill='x', expand=True)

        total = len(self.checks)
        self.checks_summary.configure(
            text=f"{ok_count} / {total} OK",
            foreground=COLOR_OK if ok_count == total else COLOR_WARN
        )

        # Enable START tylko jak no blocking failure
        blocking = any(c.status == "FAIL" and c.blocking and not self.expert_mode.get()
                       for c in self.checks)
        self.start_btn.configure(
            state='disabled' if blocking or self.is_flashing else 'normal'
        )

    def _build_progress_panel(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(fill='x', pady=5)
        ttk.Label(panel, text="Progress", style="Panel.TLabel",
                  font=FONT_BOLD, foreground=COLOR_ACCENT).pack(anchor='w')

        self.progress_bar = ttk.Progressbar(panel, mode='determinate',
                                            style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill='x', pady=(5, 5))

        self.progress_text = ttk.Label(panel, text="Pass: 0 / Packets: 0 / Bytes: 0",
                                       style="Panel.TLabel", font=FONT_BASE)
        self.progress_text.pack(anchor='w')

    def _build_log_panel(self, parent):
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(fill='both', expand=True, pady=5)
        ttk.Label(panel, text="Log", style="Panel.TLabel",
                  font=FONT_BOLD, foreground=COLOR_ACCENT).pack(anchor='w')
        self.log_text = scrolledtext.ScrolledText(
            panel, height=20, bg=COLOR_PANEL, fg=COLOR_FG,
            insertbackground=COLOR_FG, font=FONT_BASE,
            relief='flat', state='disabled', wrap='word'
        )
        self.log_text.pack(fill='both', expand=True, pady=(5, 0))

    # --- Flash actions ---
    def _on_start_flash(self):
        if self.is_flashing:
            return
        # Final confirmation
        firmware = self.firmware_path.get()
        ini = self.ini_path.get() or str(Path(firmware).with_suffix('.ini'))
        pc_ip = self._get_selected_pc_ip()
        model = MODELS.get(self.selected_model.get())

        confirm_msg = (
            f"PRZED ROZPOCZECIEM FLASH'A:\n\n"
            f"Model:       {model.name}\n"
            f"Firmware:    {os.path.basename(firmware)}\n"
            f"INI:         {os.path.basename(ini)}\n"
            f"Karta:       {self._get_selected_adapter_name()} ({pc_ip})\n"
            f"Dest:        {model.router_ip if self.use_unicast.get() else MULTICAST_IP}\n"
            f"Interval:    {self.interval_ms.get()}ms\n"
            f"Max passes:  {self.max_passes.get()}\n\n"
        )
        if model.secure_boot:
            confirm_msg += (
                "*** UWAGA: Ten model ma SECURE BOOT.\n"
                "    Software recovery jest NIEMOZLIWA.\n"
                "    Tool wysle pakiety, ale router je odrzuci.\n\n"
            )
        confirm_msg += "Wpisz UNBRICK aby kontynuowac:"

        ans = self._ask_text("Confirm flash", confirm_msg)
        if ans != "UNBRICK":
            LOG.info("Flash anulowany przez user'a")
            return

        # Build engine
        try:
            self.network_mgr.backup_state()
            dest_ip = self.unicast_ip.get() if self.use_unicast.get() else MULTICAST_IP
            self.engine = MutEngine(
                firmware_path=firmware, ini_path=ini,
                pc_ip=pc_ip, dest_ip=dest_ip, port=MULTICAST_PORT,
                interval_ms=self.interval_ms.get(),
                ttl=self.ttl.get(),
                max_passes=self.max_passes.get(),
                use_multicast=not self.use_unicast.get(),
                listen=self.listen_mode.get(),
                progress_callback=self._on_progress,
                log_callback=lambda msg, lvl='INFO': LOG.log(
                    logging.WARNING if lvl == 'WARN' else
                    (logging.ERROR if lvl == 'ERROR' else logging.INFO), msg
                )
            )
        except Exception as e:
            messagebox.showerror("Engine error", str(e))
            LOG.exception("Engine init failed")
            return

        self.is_flashing = True
        self.engine.start()
        self.start_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        LOG.info(">>> FLASH STARTED <<<")
        self._poll_engine()

    def _ask_text(self, title: str, prompt: str) -> str:
        """Modal dialog z text input."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("500x400")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=prompt, justify='left',
                  background=COLOR_BG, foreground=COLOR_FG,
                  font=FONT_BASE, wraplength=480).pack(padx=15, pady=15)
        var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=var, font=FONT_BIG)
        entry.pack(fill='x', padx=15, pady=5)
        entry.focus()

        result = [""]

        def on_ok():
            result[0] = var.get()
            dialog.destroy()

        def on_cancel():
            result[0] = ""
            dialog.destroy()

        btn_frame = ttk.Frame(dialog, style="TFrame")
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="OK", command=on_ok,
                   style="Danger.TButton").pack(side='left', padx=5)
        entry.bind('<Return>', lambda e: on_ok())
        dialog.wait_window()
        return result[0]

    def _on_stop_flash(self):
        if self.engine:
            LOG.info(">>> STOP requested <<<")
            self.engine.stop()
        self.is_flashing = False
        self.start_btn.configure(state='normal')
        self.stop_btn.configure(state='disabled')
        self._refresh_checks()

    def _on_progress(self, **kw):
        # Called from engine thread - schedule to GUI thread (Bug B3: try/except)
        try:
            if self.root.winfo_exists():
                self.root.after(0, self._update_progress_ui, kw)
        except (tk.TclError, RuntimeError):
            pass  # window destroyed

    def _update_progress_ui(self, kw):
        """Update progress + ETA + speed (Feature F6)."""
        pct = kw.get('pct', 0)
        if 'pct' in kw:
            self.progress_bar['value'] = pct
        bytes_sent = kw.get('bytes_sent', 0)
        packets = kw.get('packets', 0)
        # ETA + speed
        if self.engine and self.engine.stats.start_time:
            elapsed = time.time() - self.engine.stats.start_time
            speed_kbps = (bytes_sent / 1024.0) / elapsed if elapsed > 0 else 0
            eta_str = ""
            if pct > 0 and elapsed > 5:
                total_time = elapsed * 100.0 / pct
                remaining = max(0, total_time - elapsed)
                eta_str = f" ETA: {int(remaining/60)}m{int(remaining%60)}s"
            speed_str = f" {speed_kbps:.1f} KB/s"
        else:
            eta_str = ""
            speed_str = ""
        text = (f"Pass: {kw.get('pass_num', 0)} / "
                f"Packets: {packets:,} / "
                f"Bytes: {bytes_sent:,}")
        if 'pct' in kw:
            text += f" ({pct:.1f}%)"
        text += speed_str + eta_str
        try:
            self.progress_text.configure(text=text)
        except tk.TclError:
            pass

    def _poll_engine(self):
        """Sprawdz czy engine jeszcze dziala (Bug B3: safe winfo_exists)."""
        try:
            if not self.root.winfo_exists():
                return
        except (tk.TclError, RuntimeError):
            return
        if self.engine and self.engine.running:
            try:
                self.root.after(500, self._poll_engine)
            except tk.TclError:
                return
        else:
            was_flashing = self.is_flashing
            self.is_flashing = False
            try:
                self.start_btn.configure(state='normal')
                self.stop_btn.configure(state='disabled')
            except tk.TclError:
                return
            self._refresh_checks()
            if was_flashing:
                LOG.info(">>> FLASH FINISHED <<<")
                # Pokaz post-flash dialog (Feature F1, F5)
                self._show_post_flash_dialog()

    def _cleanup(self):
        """Atexit cleanup - restore network."""
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass

    def _open_telnet(self):
        """Otworz interaktywne telnet do routera (Feature F1, Guide.txt krok 13)."""
        model = MODELS.get(self.selected_model.get())
        ip = model.router_ip if model else DEFAULT_ROUTER_IP_AFTER_FLASH
        # Po flashu router uzywa default 192.168.1.1 dla recovery debug fw
        if model and model.router_ip != "192.168.1.1":
            if messagebox.askyesno(
                    "Telnet IP",
                    f"Po flashu debug firmware'u, router moze odpowiadac na 192.168.1.1\n"
                    f"(NIE na {model.router_ip} co jest dla normal mode).\n\n"
                    f"Uzyc 192.168.1.1?"):
                ip = "192.168.1.1"

        if self.network_mgr.open_telnet_window(ip):
            messagebox.showinfo(
                "Telnet otwarty",
                f"Otwarto okno cmd z telnet {ip}.\n\n"
                f"W otwartym oknie wpisz:\n"
                f"  diag restore default\n\n"
                f"Czekaj 5 sekund, potem zamknij okno i restart routera."
            )
        else:
            messagebox.showerror("Telnet failed",
                                  "Nie udalo sie otworzyc telnet'a. "
                                  "Sprawdz czy Telnet Client jest enabled w Windows Features.")

    def _show_led_info(self):
        """Pokaz tabele kolorow LED (Feature F5)."""
        info = (
            "=== Stany LED routera Huawei (WS7200/AX3) ===\n\n"
            "PRZED FLASH (router-cegla):\n"
            "  • Czerwona pulsujaca (bootloop)    -> firmware bad, wprowadz tryb upgrade\n"
            "  • Czerwona stala                    -> upgrade mode (OK, mozna flashowac)\n\n"
            "PODCZAS FLASH:\n"
            "  • Czerwona MIGA SZYBKO              -> transfer multicast trwa (OK!)\n"
            "  • Czerwona STALA (nie miga)         -> packetey NIE docieraja!\n"
            "      -> sprawdz: kabel, IP karty, interval (uzyj 5ms!)\n\n"
            "PO ZAKONCZENIU TRANSFERU:\n"
            "  • Czerwona MIGA WOLNO               -> NAND write w toku, NIE WYLACZAJ!\n"
            "  • Zielona STALA                     -> SUKCES! Restart routera.\n\n"
            "PO RESTARCIE:\n"
            "  • Pomaranczowo-czerwona             -> debug firmware boot (NORMAL!)\n"
            "      -> teraz: telnet 192.168.1.1 + 'diag restore default'\n"
            "  • Niebieska/zielona normalna        -> normal firmware boot OK\n"
            "  • Czerwona pulsujaca (bootloop)    -> flash failed, sprobuj ponownie\n\n"
            "E5186 (LTE):\n"
            "  • Niebieska stala  -> upgrade mode active\n"
            "  • WiFi LED blink   -> transferring\n"
            "  • WiFi LED slow blink -> done (sukces)\n"
        )
        dialog = tk.Toplevel(self.root)
        dialog.title("LED states info")
        dialog.geometry("600x500")
        dialog.configure(bg=COLOR_BG)
        text = scrolledtext.ScrolledText(
            dialog, bg=COLOR_PANEL, fg=COLOR_FG, font=FONT_BASE,
            wrap='word', state='normal', relief='flat'
        )
        text.pack(fill='both', expand=True, padx=10, pady=10)
        text.insert('1.0', info)
        text.configure(state='disabled')
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)

    def _show_about(self):
        """About dialog (Feature F8)."""
        msg = (
            f"{APP_NAME} v{APP_VERSION}\n\n"
            f"Open-source Python clone of HuaweiMUT.exe\n"
            f"Reverse-engineered z 389KB MFC binary (2008-05-15).\n\n"
            f"Wspierane modele: WS7200, AX3, Honor R3, E5186, B315, B525,\n"
            f"B535, HG630V2, HG633, HG659.\n\n"
            f"License: MIT\n"
            f"GitHub: https://github.com/<your-repo>\n\n"
            f"Credits:\n"
            f"  Jari Turkia (blog.hqcodeshop.fi) - E5186 unbrick guide\n"
            f"  micha102 - oryginalny generate_ini_file.py\n"
            f"  4PDA + XDA + OpenWrt - hardware analysis & recovery procedures\n\n"
            f"Disclaimer: Uzywasz na wlasna odpowiedzialnosc.\n"
            f"WS7200/AX3/Honor R3 maja secure boot - software recovery niemozliwa.\n"
            f"Patrz _research/FINAL_REPORT.md."
        )
        messagebox.showinfo(f"About {APP_NAME}", msg)

    def _show_post_flash_dialog(self):
        """Pokaz user'owi co zrobic po flashu (Feature F1, Guide.txt kroki 10-13)."""
        try:
            if not self.root.winfo_exists():
                return
        except (tk.TclError, RuntimeError):
            return
        model = MODELS.get(self.selected_model.get())
        secure_warning = ""
        if model and model.secure_boot:
            secure_warning = (
                "\n*** UWAGA: Ten model ma SECURE BOOT.\n"
                "Router prawdopodobnie ODRZUCIL firmware (signature check).\n"
                "Patrz _research/FINAL_REPORT.md dla hardware recovery.\n\n"
            )

        dialog = tk.Toplevel(self.root)
        dialog.title("Flash zakonczony - co dalej?")
        dialog.geometry("700x600")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self.root)

        info = scrolledtext.ScrolledText(
            dialog, bg=COLOR_PANEL, fg=COLOR_FG, font=FONT_BASE,
            wrap='word', state='normal', relief='flat', height=20
        )
        info.pack(fill='both', expand=True, padx=10, pady=10)
        info.insert('1.0',
            f"=== Flash zakonczony ({self.engine.stats.passes_completed if self.engine else 0} pass) ===\n\n"
            f"{secure_warning}"
            f"PRZED PIERWSZYM RESTARTEM SPRAWDZ DIODE:\n"
            f"  - Zielona stala = SUKCES, przejdz do kroku 1\n"
            f"  - Czerwona miga wolno = jeszcze NAND write, czekaj!\n"
            f"  - Czerwona stala = pakiety nie doszly, sprobuj jeszcze raz (przycisk H + power)\n"
            f"  - Pulsuje czerwono = bootloop, niestety flash failed\n\n"
            f"KROKI POST-FLASH (Guide.txt 10-13):\n"
            f"  1. Zielona LED -> wylacz zasilanie routera, wlacz znowu\n"
            f"  2. Po restart'cie LED bedzie POMARANCZOWO-CZERWONA = NORMAL\n"
            f"     (to debug firmware, jeszcze nie skonfigurowany)\n"
            f"  3. (Opcjonalnie) ustaw default gateway 192.168.1.1 na karcie\n"
            f"     (do tej pory bylo bez gateway, teraz potrzebne)\n"
            f"  4. Otworz Telnet do 192.168.1.1 (przycisk ponizej)\n"
            f"  5. Wpisz: diag restore default\n"
            f"  6. Czekaj 5 sekund\n"
            f"  7. Wylacz/wlacz router ostatni raz\n"
            f"  8. Router wstanie z fabryczna konfiguracja\n"
            f"  9. WiFi 'HUAWEI-...' bedzie dostepne, GUI: http://192.168.3.1\n\n"
            f"PRZYWROCENIE INTERNETU NA PC:\n"
            f"  - Kliknij 'Restore network' ponizej (DHCP + re-enable WiFi)\n"
        )
        info.configure(state='disabled')

        # Buttons
        btns = ttk.Frame(dialog, style="TFrame")
        btns.pack(fill='x', padx=10, pady=10)

        def do_telnet():
            self.network_mgr.open_telnet_window("192.168.1.1")

        def do_restore():
            adapter_name = self._get_selected_adapter_name()
            if adapter_name:
                self.network_mgr.restore_dhcp(adapter_name)
            self.network_mgr.enable_disabled_adapters()
            self.network_mgr.renew_dhcp()
            messagebox.showinfo("Restored", "Sieci przywrocono - DHCP + adapters re-enabled")

        ttk.Button(btns, text="📡 Open Telnet 192.168.1.1",
                   command=do_telnet).pack(side='left', padx=5)
        ttk.Button(btns, text="↻ Restore network",
                   command=do_restore).pack(side='left', padx=5)
        ttk.Button(btns, text="Close",
                   command=dialog.destroy).pack(side='right', padx=5)

    def _on_close(self):
        """Bug B5: Auto-restore network state przy close."""
        if self.is_flashing:
            if not messagebox.askyesno(
                    "Flash w toku!",
                    "Flash jeszcze trwa! Na pewno zamknac?\n"
                    "(Zatrzyma wysylanie i sproboje przywrocic siec)"):
                return

        # Sprawdz czy zostal static IP zostal ustawiony - oferuj restore
        if self.network_mgr.BACKUP_FILE.exists():
            if messagebox.askyesno(
                    "Przywrocic siec?",
                    "Wykryto ze siec byla zmieniana (static IP).\n\n"
                    "Przywrocic DHCP + re-enable disabled adapters?\n"
                    "(Zalecane jak skonczyles flash)"):
                adapter_name = self._get_selected_adapter_name()
                if adapter_name:
                    self.network_mgr.restore_dhcp(adapter_name)
                self.network_mgr.enable_disabled_adapters()
                self.network_mgr.renew_dhcp()
                LOG.info("Network state restored")

        self._cleanup()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ============================================================================
# 11. CLI MODE
# ============================================================================
def cli_mode(args):
    """CLI fallback - jak mut_python.py."""
    if args.list_adapters:
        print("=" * 60)
        print(f"  {APP_NAME} v{APP_VERSION} - Adaptery")
        print("=" * 60)
        adapters = list_network_adapters()
        if not adapters:
            print("  Brak kart z IPv4")
            return 1
        for i, a in enumerate(adapters):
            tag = ""
            if a.is_wifi:
                tag = " [WiFi - NIEZALECANE]"
            elif a.is_virtual:
                tag = " [virtual]"
            print(f"  [{i}] {a.ip:18s} {a.name}{tag} status={a.status}")
        auto = auto_detect_pc_ip()
        if auto:
            print(f"\nAuto-detect wybralby: {auto}")
        return 0

    if not args.firmware:
        print("BLAD: brak argumentu firmware (uzyj --gui)")
        return 1

    if not Path(args.firmware).exists():
        print(f"BLAD: plik nie istnieje: {args.firmware}")
        return 1

    ini_path = args.ini or str(Path(args.firmware).with_suffix('.ini'))

    if args.gen_ini or args.force_cfe:
        ini = generate_ini_for_firmware(args.firmware, force_cfe=args.force_cfe,
                                         ini_path=ini_path)
        if args.gen_ini:
            print(f"\n[OK] INI gotowy: {ini}")
            return 0

    if not Path(ini_path).exists():
        print(f"BLAD: INI nie istnieje: {ini_path} (uzyj --gen-ini)")
        return 1

    pc_ip = args.pc_ip or auto_detect_pc_ip()
    if not pc_ip:
        print("BLAD: nie znaleziono karty - uzyj --list-adapters")
        return 1

    print(f"PC IP: {pc_ip}")
    adapter = adapter_for_ip(pc_ip)
    if adapter and adapter.is_wifi and not args.allow_wifi:
        print(f"BLAD: {pc_ip} to karta WiFi! Uzyj --allow-wifi (NIEZALECANE)")
        return 2

    use_multicast = args.unicast is None
    dest_ip = args.unicast if args.unicast else MULTICAST_IP

    engine = MutEngine(
        firmware_path=args.firmware, ini_path=ini_path,
        pc_ip=pc_ip, dest_ip=dest_ip, port=MULTICAST_PORT,
        interval_ms=args.interval, ttl=args.ttl,
        max_passes=args.passes, use_multicast=use_multicast,
        listen=args.listen,
        log_callback=lambda msg, lvl='INFO': print(f"[{lvl}] {msg}")
    )

    print(f"Firmware: {args.firmware} ({engine.file_size:,} bytes, CRC=0x{engine.firmware_crc:08X})")
    print(f"Dest: {dest_ip}:{MULTICAST_PORT} ({'multicast' if use_multicast else 'UNICAST'})")
    print(f"Interval: {args.interval}ms, Max passes: {args.passes}")
    print("Naciśnij Ctrl+C aby przerwac.")

    engine.start()
    try:
        while engine.running:
            time.sleep(1)
            if args.verbose:
                print(f"  passes={engine.stats.passes_completed} "
                      f"packets={engine.stats.packets_sent} "
                      f"bytes={engine.stats.bytes_sent:,}")
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Stopping...")
    finally:
        engine.stop()

    print(f"\nDONE. Passes: {engine.stats.passes_completed}, "
          f"Packets: {engine.stats.packets_sent}, "
          f"Bytes: {engine.stats.bytes_sent:,}")
    return 0


# ============================================================================
# 12. MAIN ENTRY POINT
# ============================================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION} - GUI/CLI dla protokolu MUT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
PRZYKLADY:
  GUI (default):
    python unbrick_tool.py

  CLI - lista adapterow:
    python unbrick_tool.py --cli --list-adapters

  CLI - tylko wygeneruj INI:
    python unbrick_tool.py --cli firmware.bin --gen-ini --force-cfe

  CLI - flash:
    python unbrick_tool.py --cli firmware.bin --pc-ip 192.168.1.5 -v

  CLI - eksperyment unicast:
    python unbrick_tool.py --cli firmware.bin --unicast 192.168.1.1 -v

WYMAGANIA:
  - Python >= 3.7 (built-in tkinter)
  - Windows (powershell, ipconfig, netsh)
  - Administrator dla bind portu 13456 + zmiany IP
""")
    parser.add_argument('--gui', action='store_true', default=False,
                        help='Wymus GUI (default jezeli brak argumentow)')
    parser.add_argument('--cli', action='store_true', default=False,
                        help='Wymus CLI mode')
    parser.add_argument('firmware', nargs='?', help='Plik .bin firmware (CLI)')
    parser.add_argument('--ini', help='Plik .ini')
    parser.add_argument('--pc-ip', help='IP karty PC (auto-detect jak brak)')
    parser.add_argument('--list-adapters', action='store_true')
    parser.add_argument('--gen-ini', action='store_true')
    parser.add_argument('--force-cfe', action='store_true')
    parser.add_argument('--unicast', help='IP unicast zamiast multicast')
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL_MS)
    parser.add_argument('--ttl', type=int, default=DEFAULT_TTL)
    parser.add_argument('--passes', type=int, default=MAX_PASSES_DEFAULT)
    parser.add_argument('--listen', action='store_true')
    parser.add_argument('--allow-wifi', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser.parse_args()


def main():
    args = parse_args()

    # Setup logging
    setup_logging(Path.cwd())

    # CLI vs GUI decision
    # Bug B8: --gui wymusza GUI nawet z firmware argumentem (drag&drop scenario)
    if args.gui:
        use_cli = False
    else:
        use_cli = args.cli or args.list_adapters or args.gen_ini or \
                  (args.firmware is not None) or not HAS_TKINTER

    if use_cli or not HAS_TKINTER:
        if not HAS_TKINTER:
            LOG.warning("tkinter not available - falling back to CLI")
        return cli_mode(args)
    else:
        # GUI mode
        if not is_admin():
            print("UWAGA: Nie jestes Adminem. Niektore funkcje (set IP, firewall) nie zadzialaja.")
            print("       Wszystkie zabezpieczenia beda blokowac w GUI.")
            print("       Uruchom PowerShell jako Administrator i sprobuj jeszcze raz.")
            time.sleep(2)
        root = tk.Tk()
        UnbrickGUI(root)  # mainloop trzyma referencje przez root
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        LOG.exception("Fatal error")
        if HAS_TKINTER:
            try:
                messagebox.showerror("Crash", f"Fatal error:\n{e}\n\nLog: _unbrick_log_*.txt")
            except Exception:
                pass
        sys.exit(1)
