# ajazz-dock

Host driver and key launcher for the **Ajazz AKP153E** 15-key dock.

- Reads `settings.json` (JSONC — comments and trailing commas allowed)
- Pushes per-key icons to the LCD
- Listens for key presses and dispatches actions (URLs, apps, hotkeys, text, shell, macros)
- **Hot reloads** on save — edit `settings.json` and changes apply instantly

This is a clean-room reimplementation. No vendor software required.

---

## Setting up on a new computer

Runs on **Windows and macOS**. The HID protocol is identical on both; what
differs is how actions are carried out, which lives in a per-platform backend
(`ajazz_dock/backend_win32.py` / `backend_darwin.py`) picked at import time.

| | Windows | macOS |
|---|---|---|
| config | `settings.json` | `settings.macos.json` |
| launch | `start-dock.bat` | `start-dock.sh` |
| open URL | `os.startfile` | `open` |
| launch app | `subprocess.Popen` | `open -a` / `open -b` |
| hotkeys / typing | `keyboard` | `pynput` (needs Accessibility) |
| autostart | Startup folder (`.ps1`) | LaunchAgent (`.sh`) |
| icon extraction | `extract_icons.ps1` | `extract_icons_macos.py` |

Jump to [macOS setup](#macos-setup) if that is your host.

---

## Windows setup

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

<a name="macos-setup"></a>
## macOS setup

Verified on macOS 15 (Apple Silicon) with the AKP153E.

### 1. Get the project and an environment

```bash
git clone https://github.com/PatrickSun93/ajazz-dock.git
cd ajazz-dock
python3 -m venv .venv
./.venv/bin/pip install -e .
```

`hidapi` installs from a wheel — **`brew install hidapi` is not needed**.

### 2. Plug in the device

No driver, no permission prompt, no `sudo`. The AKP153E presents a single HID
interface on the vendor-defined usage page `0xFFA0`, which macOS does not seize
the way it seizes keyboards, so `hid.open()` just works.

Check the host sees it:

```bash
./.venv/bin/python -c "import hid; print([(hex(d['vendor_id']), hex(d['product_id'])) for d in hid.enumerate() if d['vendor_id']==0x0300])"
```

Should print `[('0x300', '0x1010'), ...]`.

### 3. Build the icons

Two generators, because macOS icons come from two places:

```bash
./.venv/bin/python tools/extract_icons_macos.py   # real artwork out of .app bundles
./.venv/bin/python tools/make_key_icons.py        # SF Symbol tiles for folders, stack, web
```

### 4. Run it

```bash
./start-dock.sh                    # uses settings.macos.json, logs to dock.log
./.venv/bin/python -u -m ajazz_dock settings.macos.json   # or in the foreground
./stop-dock.sh                     # stop it and leave the panel dark
```

`stop-dock.sh` sends SIGTERM, which the runner handles by clearing every key
and sleeping the panel before it exits. `kill -9` skips all that and leaves the
last page's icons glowing on a dock nothing is driving — use `./stop-dock.sh -f`
only when it will not go quietly.

### Closing Claude Code sessions

`tools/close-claude-session.sh` closes the session running in a given project,
matched by working directory (the command line is identical across all of them):

```bash
./tools/close-claude-session.sh --list                  # show, touch nothing
./tools/close-claude-session.sh /path/to/project
./tools/close-claude-session.sh --all
```

Two things it refuses to close:

- **Anything under `personalAgent-wsl`.** The mail/calendar agent runs silently
  and nothing signals that it stopped — you find out by noticing a batch of
  unprocessed mail. Hardcoded, so a bad config cannot reach it either. There is
  no key for it on page 6, and `--all` skips it.
- **The VS Code extension helper**, whose argv points into `.vscode/extensions`.
  It shares the `claude` process name with real sessions, but closing it only
  breaks the editor integration.

### 5. (Optional) Start at login

```bash
./tools/install_autostart_macos.sh
./tools/uninstall_autostart_macos.sh   # to remove
```

Installs a **LaunchAgent**, not a LaunchDaemon — agents run inside your login
session and can therefore launch apps onto your desktop, which is the same
reason the Windows side uses the Startup folder instead of a Service.

---

## macOS gotchas

Three things that cost real time to work out:

**`shell` actions run under non-interactive `/bin/sh`, so shell aliases do not
exist.** An alias defined in `~/.zshrc` — `claude7`, say — is simply not there.
Call the script by absolute path.

**`keys` and `text` actions fail silently without Accessibility permission.**
No error, no prompt, nothing happens — indistinguishable from an unbound key.
Grant it to whatever launched the dock (your terminal, or the launchd process
if it is autostarting), then **restart the dock**: pynput caches the permission
state at process start.

**launchd does not read your shell profile.** A LaunchAgent gets a minimal
`PATH`, so `claude` and everything under homebrew disappear from `shell`
actions. `install_autostart_macos.sh` sets `PATH` explicitly for this reason.

**A checkout on an external volume cannot be autostarted without granting Full
Disk Access.** launchd-spawned processes are refused `/Volumes/...` by TCC, and
being background processes they cannot raise the consent prompt — so the agent
dies with `EX_CONFIG` and writes nothing to the log. Add the interpreter
(`.venv/bin/python`) under System Settings › Privacy & Security › Full Disk
Access, or run the dock manually. `install_autostart_macos.sh` detects this
case and says so rather than leaving a silent failure.

---

## Status strip

Above the 15 keys are three display-only slots — logical slots **16, 17, 18**,
top to bottom. They take images exactly like keys but never report input.

```jsonc
"status": {
  "refresh": 60,
  "limit": 2500000,
  "slots": {
    "16": { "type": "claude_pct" },      // % of the 5h output budget left
    "17": { "type": "claude_reset" },    // time until the 5h window resets
    "18": { "type": "claude_usage", "window": "today" }
  }
}
```

| provider | shows |
|---|---|
| `claude_pct` | share of `limit` unspent this 5h window; band turns amber under 50%, red under 20% |
| `claude_reset` | minutes until the window resets; red under 30 minutes |
| `claude_usage` | raw totals for `5h` / `today` / `7d`, metric selectable via `metric` |
| `page` | current page name and index |
| `clock` | time and date |

Numbers come from `~/.claude/projects/*/*.jsonl`, which Claude Code appends a
record to per message.

**`limit` is a baseline you choose, not a real quota.** No quota is stored
anywhere on disk — not in the logs, not elsewhere under `~/.claude`, and the
CLI has no `usage` subcommand. `/usage` reads it live from the API and never
writes it down. Calibrate by running `/usage` in Claude Code and working
backwards from the percentage it reports.

The **reset time is exact**, though. A 5-hour window opens on a message, lapses
five hours later, and the next message after that opens a fresh one — a chain
the log timestamps reconstruct completely.

Refreshing never writes to the device from the worker thread: it renders tiles
into a queue that the main loop drains, keeping every HID write on one thread.

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
| `page`  | `target` (`"next"`/`"prev"`/name/index)    | `{ "type": "page", "target": "next" }`                        |

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

### Multiple pages

15 keys not enough? Define `pages` and use `page` actions to switch between
them. The runner re-pushes that page's icons on switch — paging is entirely
host-side, no special device mode.

```jsonc
{
  "$schema": "./settings.schema.json",
  "brightness": 80,

  // `shared` keys are merged into every page — define nav keys once here.
  "shared": {
    "1": { "image": "icons/prev.png", "action": { "type": "page", "target": "prev" } },
    "3": { "image": "icons/next.png", "action": { "type": "page", "target": "next" } }
  },

  "pages": [
    { "name": "main",  "keys": { /* ... */ } },
    { "name": "media", "keys": { /* ... */ } }
  ]
}
```

- `page` target: `"next"` / `"prev"` (wrap around), a page name, or a 0-based index.
- `shared` wins over a page's own binding on a key-id clash.
- A config with a top-level `keys` map (no `pages`) is just a single page —
  fully backwards compatible.

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
