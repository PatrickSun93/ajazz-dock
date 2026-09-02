# ajazz-dock

Host driver and key launcher for the **Ajazz AKP153E** 15-key dock.

- Reads a JSONC config (comments and trailing commas allowed)
- Pushes per-key icons to the LCD, and live figures to the status strip above the keys
- Listens for key presses and dispatches actions (URLs, apps, hotkeys, text, shell, macros)
- **Hot reloads** on save — edit the config and changes apply instantly
- Survives the device going away: reconnects instead of dying
- Optional child lock, because the keys stop services and quit applications

This is a clean-room reimplementation. No vendor software required.

---

## Which platform

Runs on **Windows and macOS**. The HID protocol is identical on both; what
differs is how actions are carried out, which lives in a per-platform backend
(`ajazz_dock/backend_win32.py` / `backend_darwin.py`) picked at import time.

| | Windows | macOS |
|---|---|---|
| config | `settings.json` | `settings.macos.json` |
| launch | `start-dock.bat` | `start-dock.sh` / `stop-dock.sh` |
| open URL | `os.startfile` | `open` |
| launch app | `subprocess.Popen` | `open -a` / `open -b` |
| hotkeys / typing | `keyboard` | `pynput` (needs Accessibility) |
| autostart | Startup folder (`.ps1`) | LaunchAgent (`.sh`) |
| icon extraction | `extract_icons.ps1` | `extract_icons_macos.py` + `make_key_icons.py` |

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

### 5. (Optional) Start at login

```bash
./tools/install_autostart_macos.sh
./tools/uninstall_autostart_macos.sh   # to remove
```

Installs a **LaunchAgent**, not a LaunchDaemon — agents run inside your login
session and can therefore launch apps onto your desktop, which is the same
reason the Windows side uses the Startup folder instead of a Service.
The runner waits for the dock if it is not there at launch, so one plugged in
after login gets picked up rather than staying dark; `KeepAlive` restarts the
runner if it ever dies anyway.

On an external volume this needs Full Disk Access for the *interpreter* — see
[macOS gotchas](#macos-gotchas). The installer detects the failure and prints
the exact path to grant.

---

## Features

### Status strip

Above the 15 keys are three display-only slots — logical slots **16, 17, 18**,
top to bottom. They take images exactly like keys but never report input. The
protocol always addressed them; the runner just never used to.

```jsonc
"status": {
  "refresh": 60,
  "slots": {
    "16": { "type": "claude_pct" },        // 5h quota left
    "17": { "type": "claude_reset" },      // countdown to the 5h reset
    "18": { "type": "claude_week_pct" }    // weekly quota left
  }
}
```

| provider | shows |
|---|---|
| `claude_pct` | share of the 5h quota left; band turns amber under 50%, red under 20% |
| `claude_reset` | time until the 5h window resets; red under 30 minutes |
| `claude_week_pct` | share of the weekly quota left |
| `claude_week_reset` | time until the weekly quota rolls over |
| `claude_usage` | raw token totals for `5h` / `today` / `7d`, metric selectable via `metric` |
| `page` | current page name and index |
| `clock` | time and date |

Refreshing never writes to the device from the worker thread: it renders tiles
into a queue that the main loop drains, keeping every HID write on one thread.

#### Where the numbers come from

**Preferred: the real figures.** Since Claude Code 2.1.x the JSON handed to a
statusline command on stdin carries a `rate_limits` block for Pro/Max
subscribers — the same figures `/usage` prints, with no API call. That is the
only place they exist outside `/usage` itself: nothing is written to disk, and
the CLI has no `usage` subcommand.

```bash
cp tools/statusline-usage.py ~/.claude/
# then in ~/.claude/settings.json:
#   "statusLine": {"type": "command",
#                  "command": "/usr/bin/python3 /Users/<you>/.claude/statusline-usage.py"}
```

It captures the block every turn into `~/.claude/rate-limits.json`, which the
strip reads. Keep the script in `~/.claude/`, not in the repo: this checkout may
live on an external volume, and a statusline command that cannot be read takes
the terminal's status line down with it.

**Stale beats estimated.** A snapshot only refreshes while some session is
taking turns. Past 30 minutes it is shown greyed with its age (`45分钟前`)
rather than replaced by an estimate — an old real figure is close, and the
estimate is not. Past 6 hours it is dropped. If the 5h window it describes has
since lapsed, the tile shows `?` rather than a percentage that is certainly
wrong in the optimistic direction.

**The estimate is a last resort, and it does not work well.** With no hook at
all, the strip sums `usage` blocks out of `~/.claude/projects/*/*.jsonl` and
divides by `limit` / `week_limit`. Tiles from this path are prefixed `~`.

Do not trust the number. Measured 2026-08-28, the real weekly figure was **31%
left while the estimate said 56%** — and the error runs in the dangerous
direction, overstating what remains. Every proxy tried (output tokens, output +
cache writes, total tokens, message count) drifted 0.6–0.8x against a
calibration taken four days earlier, and the weekly denominator itself moves: a
`+50% weekly limits` promo shifts it by roughly the 1.5x that drift showed.
Anthropic's weighting is not published and the quota is not constant, so no
local sum reproduces it.

Install the hook. The estimate exists so the strip degrades to *something*, not
because that something is reliable.

`week_anchor` is one observed reset instant; periods repeat every 7 days from
it, forwards and backwards, so it never needs updating.

### Child lock

The dock sits within reach, and its keys stop services and quit applications.
`lock` makes the panel inert until a sequence of key positions is entered.

```jsonc
"lock": {
  "code": [1, 2, 3, 4],        // key ids, in order
  "image": "icons/locked.png",
  "idle_minutes": 0,           // 0 disables auto-lock
  "start_locked": false,
  "hint": true                 // label the unlock keys ➊➋➌➍
}
```

A key with `{ "type": "lock" }` locks on demand.

**Why a sequence and not a long press:** the device reports presses only —
there is no release event in the input frame — so there is nothing to time a
hold against. A sequence is the only gesture this hardware can distinguish.

**`hint` labels the unlock keys ➊➋➌➍ on the lock screen** and leaves every
other key as a plain 🔒. It is on by default, which does put the code on the
face of the lock — but this guards against small hands, and the failure that
actually happens is an adult who cannot get back in. Set it to `false` and
every tile becomes identical, giving away nothing about which positions the
code uses.

Matching runs over a sliding window, so a burst of random presses followed by
the right sequence still opens it — which is the whole situation it exists for.
A lock with no `code` refuses to engage rather than locking itself shut
permanently, and a config reload keeps the locked state (so the code can be
changed while locked, and the new one works immediately).

Locked presses are logged with a progress bar (`● ● ○  2/3`), because a panel
that shows nothing back is unusable to press into — you cannot tell a key that
did not register from a code you are entering wrong.

**Forgotten the code?** Restart the dock: `./stop-dock.sh && ./start-dock.sh`.
`start_locked` defaults to false, so it comes back unlocked. This stops a
four-year-old, not anyone holding a terminal.

### Stopping services

Stopping a service means stopping whatever it spawned — for a tmux-based agent
runner, that includes the Claude Code sessions inside it. Bind those to `shell`
actions running through `tools/run-in-iterm.sh` so the output stays visible; a
backgrounded stop that takes minutes looks identical to a key that did nothing.

Graceful and immediate stops deserve **separate keys**. A graceful shutdown that
waits for agents to finish their round can take many minutes, and the situation
that calls for an immediate one — a runaway loop burning quota — is exactly the
situation where you cannot wait it out.

### Closing individual Claude Code sessions

`tools/close-claude-session.sh` is a command-line tool (no key bound by default)
that closes the session running in a given project, matched by working directory
since the command line is identical across all of them:

```bash
./tools/close-claude-session.sh --list                  # show, touch nothing
./tools/close-claude-session.sh /path/to/project
./tools/close-claude-session.sh --all
```

Two things it refuses to close:

- **Anything under a protected path** (`PROTECTED_DIRS` in the script). A
  background agent that runs silently gives no sign that it stopped — you find
  out later, from the work it did not do. Hardcoded, so a bad config cannot
  reach it either, and `--all` skips it.
- **The VS Code extension helper**, whose argv points into `.vscode/extensions`.
  It shares the `claude` process name with real sessions, but closing it only
  breaks the editor integration.

---

<a name="macos-gotchas"></a>
## macOS gotchas

Four things that cost real time to work out.

**`shell` actions run under non-interactive `/bin/sh`, so shell aliases do not
exist.** An alias defined in `~/.zshrc` is simply not there. Call the script by
absolute path.

**`keys` and `text` actions fail silently without Accessibility permission.**
No error, no prompt, nothing happens — indistinguishable from an unbound key.
Grant it to whatever launched the dock (your terminal, or the launchd process
if it is autostarting), then **restart the dock**: pynput caches the permission
state at process start.

**launchd does not read your shell profile.** A LaunchAgent gets a minimal
`PATH`, so homebrew and `~/.local/bin` disappear from `shell` actions.
`install_autostart_macos.sh` sets `PATH` explicitly for this reason.

**Autostarting a checkout on an external volume needs Full Disk Access — for
the interpreter, not for the plist.** TCC grants that permission per
executable, which makes the failure confusing to diagnose:

- If `/bin/bash` is already granted, it can `cd` into the volume and open a log
  there, so the plist looks completely healthy. A probe running `date` writes
  fine, which sends you looking in the wrong place.
- `python` is a separate binary with separate permission. Without it, it cannot
  read the `.py` files or site-packages off the volume — the process starts and
  writes *nothing at all*. Not an error, not a traceback. It reads like a hang.

Grant it to the interpreter's real path, which for a venv is the framework it
symlinks to, not the venv's own `bin/python`:

```bash
./.venv/bin/python -c 'import os,sys; print(os.path.realpath(sys.executable))'
# add the sibling Resources/Python.app under Full Disk Access
```

Separately, nothing in the plist should name a path on that volume:
`WorkingDirectory` and `StandardOutPath` are accesses **launchd itself**
performs, and either one pointing at a removable volume kills the job with
`EX_CONFIG` before the program runs, log empty. Let bash do the `cd` and the
redirect — which is what `install_autostart_macos.sh` generates.

---

## Config reference

JSONC with a `$schema` link that gives VS Code autocomplete and validation.

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

Column-major from the bottom-left:

```
 col1  col2  col3
  13    14    15
  10    11    12
   7     8     9
   4     5     6
   1     2     3
```

Which end is "top" depends on how the dock sits. The numbering above assumes
the status strip is at the **bottom**. Sitting it the other way round — strip at
the top, which is the natural reading order — puts 1/2/3 nearest the strip and
13/14/15 nearest your hand. Nothing in the software cares; just be consistent
about which orientation your icons and lock code assume.

### Binding fields

| field    | type     | required | notes                                                |
|----------|----------|----------|------------------------------------------------------|
| `image`  | string   | no       | Path to PNG/JPG. Auto-resized to 95×95 + rotated 90° |
| `action` | object   | no       | See action types below                               |

Omit `image` to leave the LCD dark. Omit `action` to make the key a no-op.

Images with transparency are flattened onto black or white depending on how
dark the artwork is, measured over the opaque pixels — a black-on-transparent
logo composited onto black would otherwise vanish entirely.

### Action types

| type    | fields                          | example                                                                  |
|---------|---------------------------------|--------------------------------------------------------------------------|
| `url`   | `target`                        | `{ "type": "url", "target": "https://github.com" }`                      |
| `app`   | `target`, `args?`               | `{ "type": "app", "target": "Google Chrome" }`                           |
| `keys`  | `target` (hotkey combo)         | `{ "type": "keys", "target": "ctrl+shift+f" }`                           |
| `text`  | `target` (literal text)         | `{ "type": "text", "target": "hello world" }`                            |
| `shell` | `target` (shell command line)   | `{ "type": "shell", "target": "open ~/Downloads" }`                      |
| `macro` | `steps` (array of actions or `{delay: N}`) | see below                                                     |
| `page`  | `target` (`"next"`/`"prev"`/name/index)    | `{ "type": "page", "target": "next" }`                        |
| `lock`  | none                            | `{ "type": "lock" }` — engage the child lock                             |

On macOS an `app` target may be an application name, a `.app` path, a bundle id
(`open -b`), or a plain executable path (run directly).

Macro example — open an editor, wait, type, press Enter:

```jsonc
{
  "type": "macro",
  "steps": [
    { "type": "app",  "target": "TextEdit" },
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

With the `$schema` line in your config, VS Code highlights invalid actions,
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
| `PYTHON`            | Interpreter used by `start-dock.sh`                          |

---

## Project layout

```
ajazz_dock/
    __init__.py         # public API: DockDevice, Config, actions
    __main__.py         # python -m ajazz_dock entry
    device.py           # HID protocol (CRT\0\0 commands, JPEG push, reconnect)
    actions.py          # action dispatcher + platform backend selection
    backend_darwin.py   # macOS: open / open -a / pynput
    backend_win32.py    # Windows: os.startfile / Popen / keyboard
    config.py           # JSONC loader + thread-safe Config holder
    runner.py           # main loop: hot reload, image diffing, key dispatch
    status.py           # status strip (slots 16-18): providers + render + worker
    live_limits.py      # real rate limits, published by the statusline hook
    claude_usage.py     # token totals from session logs (the fallback estimate)
    lock.py             # child lock: unlock sequence, auto-lock
tools/
    statusline-usage.py         # Claude Code statusline hook -> rate-limits.json
    run-in-iterm.sh             # open an iTerm window and run something in it
    close-claude-session.sh     # close a project's Claude Code session
    extract_icons_macos.py      # pull artwork out of installed .app bundles
    make_key_icons.py           # SF Symbol gradient tiles
    make_icon.py                # plain labelled tile (both platforms)
    install_autostart_macos.sh  # LaunchAgent
    uninstall_autostart_macos.sh
    install_autostart.ps1       # Windows Startup folder
    uninstall_autostart.ps1
    extract_icons.ps1           # Windows icon extraction
start-dock.sh / stop-dock.sh    # macOS launcher and graceful stop
settings.json                   # Windows config
settings.macos.json             # macOS config
settings.schema.json            # JSON schema for VS Code autocomplete
icons/                          # icon files
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

Keys are 1..15, **column-major from the bottom-left** corner. Slots 16, 17 and
18 are the display-only status strip; they accept images the same way and never
report input.

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

**A key logs `-> shell` but nothing happens** — check `dock.log` for the
script's stderr, which the runner inherits. `Permission denied` there means the
executable bit was lost: this repo has `core.fileMode=false`, so git records
scripts as `100644` and a checkout recreates them non-executable. Fixed two
ways — `git update-index --chmod=+x` for the index, and configs invoking
scripts as `bash <path>` so a fresh clone works regardless.

**The status strip is not updating** — `dock.log` prints `[status] 已推送槽`
on every push, so check there first. If pushes are happening, the numbers
genuinely have not moved: a weekly percentage against a ~28M denominator only
shifts about half a point per day. If the log shows `[device] 等待设备回来…`
instead, the dock has dropped off the USB bus and the runner is waiting for
it: unplug and replug the dock (or the hub it hangs off).

**The dock stopped after the device blipped** — it shouldn't; `DockDisconnected`
is caught around the whole loop and the runner reconnects with backoff. If it
did die, `dock.log` has the traceback.

**Autostart installs but nothing runs, log empty** — see
[macOS gotchas](#macos-gotchas); on an external volume this is almost always
the interpreter missing Full Disk Access.
