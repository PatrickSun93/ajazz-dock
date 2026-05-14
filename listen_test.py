"""
Minimal listen-only sanity test. No DockDevice abstraction, no init, no
output reports. Opens VID 0x0300 PID 0x1010 and dumps anything it reads.

This is the cleanest possible apples-to-apples vs probe.py — if probe.py
listen prints frames and this doesn't, the difference is between the two
scripts. If neither prints frames, the device is in a stuck state and
needs to be unplugged/replugged.
"""

from __future__ import annotations

import time

import hid

VID = 0x0300
PID = 0x1010


def main() -> int:
    dev = hid.device()
    try:
        dev.open(VID, PID)
    except OSError as e:
        print(f"open failed: {e!r}")
        print("  device may be held by another process, or unplugged.")
        return 1

    dev.set_nonblocking(True)
    print(f"opened VID=0x{VID:04x} PID=0x{PID:04x}")
    print(f"  product:  {dev.get_product_string()!r}")
    print(f"  manuf:    {dev.get_manufacturer_string()!r}")
    print()
    print("press any key on the dock. Ctrl-C to stop.")
    print()

    t0 = time.time()
    polls = 0
    last_status = t0
    try:
        while True:
            data = dev.read(512, timeout_ms=100)
            polls += 1
            now = time.time()
            if data:
                head = " ".join(f"{b:02x}" for b in bytes(data)[:24])
                print(f"[{now-t0:7.3f}s] {len(data):>3}B  {head}")
            elif now - last_status >= 3.0:
                print(f"[{now-t0:7.3f}s] (no data — polls so far: {polls})")
                last_status = now
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        dev.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
