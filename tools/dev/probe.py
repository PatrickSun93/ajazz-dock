"""
Ajazz Stream Dock AKP53E probe.

Usage:
    python tools/dev/probe.py list                      # list all HID devices, highlight likely candidates
    python tools/dev/probe.py listen <vid> <pid>        # open device and dump raw input reports
    python tools/dev/probe.py listen <vid> <pid> <path> # disambiguate when multiple interfaces share VID/PID

VID/PID accept hex (0x0300) or decimal. `path` is the bytes string from `list` output.
"""

from __future__ import annotations

import sys
import time
from typing import Optional

import hid


AJAZZ_HINTS = ("ajazz", "akp", "stream dock", "mirabox", "streamdock")


def parse_id(s: str) -> int:
    s = s.strip().lower()
    return int(s, 16) if s.startswith("0x") else int(s)


def cmd_list() -> None:
    devs = hid.enumerate()
    if not devs:
        print("No HID devices found. Is the device plugged in?")
        return

    print(f"Found {len(devs)} HID interfaces:\n")
    candidates = []
    for d in devs:
        name = f"{d.get('manufacturer_string') or ''} {d.get('product_string') or ''}".strip().lower()
        is_candidate = any(h in name for h in AJAZZ_HINTS)
        marker = "  >>> " if is_candidate else "      "
        print(
            f"{marker}VID=0x{d['vendor_id']:04x} PID=0x{d['product_id']:04x} "
            f"iface={d.get('interface_number')} usage_page=0x{d.get('usage_page', 0):04x} "
            f"usage=0x{d.get('usage', 0):04x}"
        )
        print(f"        product = {d.get('product_string')!r}")
        print(f"        mfr     = {d.get('manufacturer_string')!r}")
        print(f"        serial  = {d.get('serial_number')!r}")
        print(f"        path    = {d.get('path')!r}")
        print()
        if is_candidate:
            candidates.append(d)

    if candidates:
        first = candidates[0]
        print(
            f"Likely Ajazz: VID=0x{first['vendor_id']:04x} PID=0x{first['product_id']:04x}\n"
            f"Next: python tools/dev/probe.py listen 0x{first['vendor_id']:04x} 0x{first['product_id']:04x}"
        )
    else:
        print(
            "No obvious Ajazz match by name. Pick the candidate whose product/mfr looks right "
            "and run: python tools/dev/probe.py listen <vid> <pid>"
        )


def _open(vid: int, pid: int, path: Optional[bytes]):
    dev = hid.device()
    if path is not None:
        dev.open_path(path)
    else:
        dev.open(vid, pid)
    dev.set_nonblocking(True)
    return dev


def _decode(buf: bytes) -> str:
    # Known frame: 41 43 4b 00 00 4f 4b 00 00 <key> 00 ...
    if len(buf) >= 10 and buf[:9] == b"ACK\x00\x00OK\x00\x00":
        key = buf[9]
        # show first 24 bytes raw too, in case other bytes start to vary
        head = " ".join(f"{b:02x}" for b in buf[:24])
        return f"key={key:>3}  raw[0:24]={head}"
    # unknown frame: dump first 32 bytes
    head = " ".join(f"{b:02x}" for b in buf[:32])
    return f"UNKNOWN raw[0:32]={head}"


def cmd_listen(vid: int, pid: int, path: Optional[bytes] = None) -> None:
    dev = _open(vid, pid, path)
    print(f"Opened VID=0x{vid:04x} PID=0x{pid:04x}")
    print(f"  manufacturer: {dev.get_manufacturer_string()!r}")
    print(f"  product:      {dev.get_product_string()!r}")
    print(f"  serial:       {dev.get_serial_number_string()!r}")
    print()
    print("Listening. Ctrl-C to stop. (auto-reconnects on read error)\n")

    t0 = time.time()
    reopen_backoff = 0.5
    try:
        while True:
            try:
                data = dev.read(256, timeout_ms=100)
            except OSError as e:
                print(f"[{time.time()-t0:7.3f}s] read error: {e!r} — reopening in {reopen_backoff:.1f}s")
                try:
                    dev.close()
                except Exception:
                    pass
                time.sleep(reopen_backoff)
                reopen_backoff = min(reopen_backoff * 2, 5.0)
                try:
                    dev = _open(vid, pid, path)
                    print(f"[{time.time()-t0:7.3f}s] reopened")
                    reopen_backoff = 0.5
                except Exception as e2:
                    print(f"[{time.time()-t0:7.3f}s] reopen failed: {e2!r}")
                continue

            if not data:
                continue
            buf = bytes(data)
            ts = time.time() - t0
            print(f"[{ts:7.3f}s] {_decode(buf)}")
    finally:
        try:
            dev.close()
        except Exception:
            pass


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1

    cmd = argv[1]
    if cmd == "list":
        cmd_list()
        return 0
    if cmd == "listen":
        if len(argv) < 4:
            print("usage: python tools/dev/probe.py listen <vid> <pid> [path]")
            return 1
        vid = parse_id(argv[2])
        pid = parse_id(argv[3])
        path = argv[4].encode("utf-8") if len(argv) > 4 else None
        cmd_listen(vid, pid, path)
        return 0

    print(f"Unknown command: {cmd}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
