"""
Minimal single-image smoke test.

Pushes ONE image to ONE key (default key 1, default icons/github.png), then
optionally listens for key presses for a few seconds so we can see whether
input still works after the image push.

Usage:
    python image_test.py                          # key 1, icons/github.png, listen 5s
    python image_test.py 13                       # different key
    python image_test.py 13 icons/claude.png      # different key + image
    python image_test.py 13 icons/claude.png 20   # also listen for 20s

If the dock LCD under the chosen key shows the image AND key presses still
get printed during the listen phase, the protocol implementation is correct
and any bug in dock.py is at a higher layer (batching, watchdog, etc).

If the image appears but key presses do NOT come through, the batch-commit
suspicion was wrong and something about the image upload itself is still
hanging the input channel.

If the image does NOT appear, the bug is in the protocol bytes themselves
(endianness, dimensions, header layout, JPEG encoding).
"""

from __future__ import annotations

import sys
import time

from device import DockDevice


def main() -> int:
    key = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    image_path = sys.argv[2] if len(sys.argv) > 2 else "icons/github.png"
    listen_secs = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    print(f"opening dock...")
    dock = DockDevice()
    try:
        print(f"init (DIS + LIG)")
        dock.init()

        print(f"set_brightness(80)")
        dock.set_brightness(80)

        print(f"set_image(key={key}, {image_path!r})")
        dock.set_image(key, image_path)

        print(f"flush (STP)")
        dock.flush()

        print(f"\nlooking at key {key} on the dock — is there an image?")
        print(f"listening for key presses for {listen_secs}s. press dock keys now.\n")

        t0 = time.time()
        while time.time() - t0 < listen_secs:
            k = dock.read_key(timeout_ms=100)
            if k is not None:
                print(f"  [{time.time()-t0:5.2f}s] key {k}")
        print("\ndone.")
    finally:
        dock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
