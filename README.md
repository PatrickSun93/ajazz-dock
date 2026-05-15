# ajazz-dock

Host driver and key launcher for the **Ajazz AKP153E** 15-key dock.

- Reads `settings.json` (JSONC — comments and trailing commas allowed)
- Pushes per-key icons to the LCD
- Listens for key presses and dispatches actions (URLs, apps, hotkeys, text, shell, macros)
- **Hot reloads** on save — edit `settings.json` and changes apply instantly

This is a clean-room reimplementation. No vendor software required.

---

## Setting up on a new computer

Windows only (the device, the `keyboard` lib, and the shell actions are all Win32).

### 1. Install Python

Either works — pick one:

**Miniconda** (recommended — `hidapi` installs without a compiler):

Download from <https://docs.conda.io/en/latest/miniconda.html>, install, open a fresh PowerShell.

**Plain Python 3.10+:**
```powershell
winget install Python.Python.3.11
```

### 2. Get the project

```powershell
git clone https://github.com/PatrickSun93/ajazz-dock.git
cd ajazz-dock
```

### 3. Install dependencies

**With conda:**
```powershell
conda env create -f environment.yml
conda activate ajazzreplace
```

**With pip:**
```powershell
pip install -e .
```

### 4. Plug in the device

USB plug — Windows recognises the AKP153E as a generic HID device, **no driver needed**. Do **not** install Ajazz's official software; it grabs the device handle and blocks this driver.

Quick check the host can see it:

```powershell
python -c "import hid; [print(f\"{d['vendor_id']:#06x}:{d['product_id']:#06x}  {d['product_string']}\") for d in hid.enumerate() if d['vendor_id']==0x0300]"
```

Should print `0x0300:0x1010  ...`.

### 5. Run it

```powershell
python -m ajazz_dock                       # uses ./settings.json
python -m ajazz_dock path\to\other.json    # custom path
ajazz-dock                                 # if installed via pip
```

You should see:

```
ajazz-dock ready. 15 keys, config=settings.json, watching for changes.
```

Press a key — it logs `key  N  -> <action type>` and fires.

### 6. (Optional) Start at login

One script generates a hidden launcher and drops it into your per-user
Startup folder, so the dock comes up automatically at every logon:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
```

Pass `-PythonExe` if your interpreter isn't the default conda env path:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1 -PythonExe "C:\path\to\python.exe"
```

It needs no admin rights, runs hidden (no console window), and logs to
`dock.log`. It also prints a `start now:` command so you don't have to
wait for the next logon. To remove it:

```powershell
powershell -ExecutionPolicy Bypass -File tools\uninstall_autostart.ps1
```

> **Why not a Windows Service?** A real service runs in session 0,
> isolated from your desktop — it could not send keystrokes or launch
> apps into your session. The Startup-folder launcher runs *in* your
> session, which is exactly what this program needs.

---

## settings.json

Looks just like Windows Terminal's settings file: JSONC with a `$schema` link
that gives VS Code autocomplete and validation.

```jsonc
{
  "$schema": "./settings.schema.json",
  "brightness": 80,
  "keys": {
    "1":  { "image": "icons/github.png", "action": { "type": "url", "target": "https://github.com" } },
    "13": { "image": "icons/claude.png", "action": { "type": "url", "target": "https://claude.ai" } }
  }
}
```

### Key layout

Column-major, numbered so they match physical position when the dock sits upright:

```
 col1  col2  col3
  13    14    15   <- row 1 (top)
  10    11    12
   7     8     9
   4     5     6
   1     2     3   <- row 5 (bottom)
```

### Binding fields

| field    | type     | required | notes                                                |
|----------|----------|----------|------------------------------------------------------|
| `image`  | string   | no       | Path to PNG/JPG. Auto-resized to 95×95 + rotated 90° |
| `action` | object   | no       | See action types below                               |

Omit `image` to leave the LCD dark. Omit `action` to make the key a no-op.

### Action types

| type    | fields                          | example                                                                  |
|---------|---------------------------------|--------------------------------------------------------------------------|
| `url`   | `target`                        | `{ "type": "url", "target": "https://github.com" }`                      |
| `app`   | `target`, `args?`               | `{ "type": "app", "target": "C:\\Windows\\System32\\notepad.exe" }`      |
| `keys`  | `target` (hotkey combo)         | `{ "type": "keys", "target": "ctrl+shift+f" }`                           |
| `text`  | `target` (literal text)         | `{ "type": "text", "target": "hello world" }`                            |
| `shell` | `target` (shell command line)   | `{ "type": "shell", "target": "rundll32.exe user32.dll,LockWorkStation" }` |
| `macro` | `steps` (array of actions or `{delay: N}`) | see below                                                     |

Macro example — open Notepad, wait, type, press Enter:

```jsonc
{
  "type": "macro",
  "steps": [
    { "type": "app",  "target": "notepad.exe" },
    { "delay": 0.6 },
    { "type": "text", "target": "macro fired" },
    { "type": "keys", "target": "enter" }
  ]
}
```

---

## VS Code tip

With the `$schema` line in `settings.json`, VS Code highlights invalid actions,
autocompletes field names, and shows inline descriptions on hover. No extension
needed.

---

## Environment variables

| var                 | effect                                                       |
|---------------------|--------------------------------------------------------------|
| `DOCK_SKIP_INIT=1`  | Skip the init handshake (device already awake)               |
| `DOCK_SKIP_IMAGES=1`| Skip image push (debug input only)                           |
| `DOCK_DEBUG=1`      | Dump unrecognized HID input frames to stderr                 |
| `DOCK_IMAGE_W/H`    | Override image size (default 95×95)                          |
| `DOCK_IMAGE_ROTATE` | Rotate before sending (default 90°)                          |

---

## Project layout

```
ajazz_dock/
    __init__.py      # public API: DockDevice, Config, actions
    __main__.py      # python -m ajazz_dock entry
    device.py        # HID protocol (CRT\0\0 commands, JPEG image push)
    actions.py       # action dispatcher (url/app/keys/text/shell/macro)
    config.py        # JSONC loader + thread-safe Config holder
    runner.py        # main loop: hot reload, image diffing, key dispatch
settings.json        # your config
settings.schema.json # JSON schema for VS Code autocomplete
icons/               # your icon files
```

---

## Device protocol cheat sheet

- **VID** 0x0300, **PID** 0x1010, protocol v1
- Every output report is 512 bytes, report ID 0, prefixed `CRT\0\0`
- **Init**: `CRT\0\0DIS` then `CRT\0\0LIG\0\0\0\0`
- **Brightness**: `CRT\0\0LIG\0\0<pct>` (0..100)
- **Image header**: `CRT\0\0BAT\0\0<size BE u16><keyId>` followed by JPEG payload in 512-byte chunks
- **Batch commit**: `CRT\0\0STP` — send **once** after a batch, not per image (this is the gotcha)
- **Clear key**: `CRT\0\0CLE\0\0\0<keyId>` (0xFF = all)
- **Image format**: JPEG, 95×95, pre-rotated 90°
- **Input frame**: 512-byte read, `ACK\0\0OK\0\0<keyId>` at bytes 0..9. Press-only — no release event.

Keys are 1..15, **column-major from the bottom-left** corner.

---

## Troubleshooting

**Device not found** — make sure no other app (Ajazz's official tool, another
Python process) is holding the HID handle. Replug the device.

**Key presses don't register after image push** — you're probably sending `STP`
after every image instead of once at the end of the batch. The runner already
does this correctly; if you're using the library directly, call `dock.flush()`
once after all `dock.set_image()` calls.

**Icons look squished or sideways** — tweak `DOCK_IMAGE_ROTATE` (try 0, 180, 270).
The AKP153E expects 90°; other variants in the family may differ.
