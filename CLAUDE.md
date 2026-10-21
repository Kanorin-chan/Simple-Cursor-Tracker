# Simple-Cursor-Tracker — CLAUDE.md

## ⛔ STOP. Read before you write.

1. `README.md` — features, hotkeys, files written, known issues
2. `cursortracker.py` — the whole app, one module-level script

Where the README and the code disagree, **the code is right.** Fix the README then and there.
Search before writing any function; it probably exists in that one file.

## Project specifics

- **Stack:** Python 3.12, pygame 2.6, Windows only. Deps in `requirements.txt`.
- **Entry point:** `cursortracker.py` runs at module level (no `main()`). Startup order:
  OTD `Settings.json` dialog → bundled daemon detects tablet (3 s) → area from `Settings.json`
  → physical size from `Configurations/<Brand>/<Model>.json` → load last preset → `while running:` loop.
- **Run it:** `python cursortracker.py` from the repo root, tablet plugged in.
- **Tests:** none. Verify by running it with a real tablet.

## Conventions that will bite you

- **Local branch `overhaul-2026-03`** (unpushed) refactored this into classes and broke tablet input.
  Change `main` in small steps the owner confirms on his tablet.
- **No tablet detected = crash** (`target_tablet` only set on the detect path).
- **Hotkeys fire on KEYUP**; `1`/`2`/`3` only work while the Alt menu is open.
- **Scripted input:** SDL ignores `SendInput` keys without `KEYEVENTF_SCANCODE`.
- **`show_message()` blocks the loop** (`pygame.time.wait`) for its whole duration.
- **`import pyautogui` makes the process system-DPI-aware**; the 800×600 window shrinks on a 100% monitor.
