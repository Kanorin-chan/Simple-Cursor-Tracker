# Simple-Cursor-Tracker — CLAUDE.md

## ⛔ STOP. Read before you write.

1. `README.md` — features, hotkeys, files written, known issues
2. `cursortracker.py` — the whole app, one module-level script

Where the README and the code disagree, **the code is right.** Fix the README then and there.
Search before writing any function; it probably exists in that one file.

## Project specifics

- **Stack:** Python 3.12, pygame 2.6, Windows only. pygame is the only dependency; Win32 calls go
  through `ctypes`, dialogs through stdlib tkinter. Don't add packages back (exe size).
- **Entry point:** `cursortracker.py` runs at module level (no `main()`). Startup order:
  OTD `Settings.json` dialog → bundled daemon detects tablet (3 s) → area from `Settings.json`
  → physical size from `Configurations/<Brand>/<Model>.json` → load last preset → `while running:` loop.
- **Run it:** `python cursortracker.py` from the repo root, tablet plugged in.
- **Tests:** none. Verify by running it with a real tablet.
- **Build:** `build.bat` → `dist\CursorTracker.exe` from `CursorTracker.spec`, in a `.buildenv` venv holding
  only pygame + PyInstaller. The spec drops unused pygame DLLs and stdlib modules; before excluding
  more, check the module isn't in a live run's `sys.modules`.
- **Detector daemon:** `OpenTabletDriver.CustomDaemon.exe` = OTD 0.6.7 daemon with the `Instance` and `RpcHost`
  names renamed to `OpenTabletDriver.Daemon.CustomDaemon` (so it never collides with the user's running OTD).
  Rebuild recipe in README → "Rebuild the detector daemon". Keep `Configurations/` on the same OTD tag.
  The 0.6.5.1 build is in `..\Simple-Cursor-Tracker-archive\otd-daemon-0.6.5.1\`.

## Conventions that will bite you

- **Local branch `overhaul-2026-03`** (unpushed) refactored this into classes and broke tablet input.
  Change `main` in small steps the owner confirms on his tablet.
- **Hotkeys fire on KEYUP**; `1`/`2`/`3` only work while the Alt menu is open.
- **Scripted input:** SDL ignores `SendInput` keys without `KEYEVENTF_SCANCODE`.
- **`show_message()` blocks the loop** (`pygame.time.wait`) for its whole duration.
- **DPI:** `user32.SetProcessDPIAware()` runs before `pygame.init()`. Every coordinate assumes it (cursor
  = `GetCursorPos`, screen = `GetSystemMetrics`); the 800×600 window shrinks on a 100% monitor.
- **Idle skip:** the loop draws nothing while the cursor, trail and input are unchanged and no panel is
  open (`last_frame_state`, `had_events`). On-screen state that changes on its own must force a redraw.
  A trail of 2+ points is still fading, so it always redraws.
- **Cursor sampler:** daemon thread `sample_cursor()` polls `get_cursor_pos()` every 1 ms (8 ms after 0.5 s still)
  and queues only changes in `cursor_samples`; once it starts, nothing else may call `get_cursor_pos()` (shared
  POINT buffer). The loop drains the queue each frame into `smooth_trail_to()`, then `prune_trail()`.
- **Active area is OTD's convention:** `active_area_values` = [X, Y, W, H, Rotation], X/Y = the area's CENTRE in mm.
  Convert only where you draw or map: `screen_to_tablet()` (cursor px → tablet mm, inverse of OTD's
  `AbsoluteOutputMode.CalculateTransformation`) and `tablet_to_minimap()` (mm → letterboxed mini-map px). `display_area` is
  OTD's display area in cursor px; OTD counts its X/Y from the virtual-desktop top-left (`VIRTUAL_X/Y`, read per-monitor aware).
  The loop rebuilds `active_area_values` from the `active_area_*` scalars every frame: edits must set those, and a preset's area never applies.
- **Trail is time-based:** points carry `trail_times`. Length = (N-1)/60 s, smoothness = time constant
  (1-s)/(60·s) (same lag as the old per-frame step), fade = point age. The preset JSON keeps the old 60 fps numbers.
  The panel shows length in ms and calls `smooth_factor` *Follow speed*.
- **Mini-map view:** `tablet_to_minimap()` frames `minimap_view` (mm): the whole tablet, or with *Zoom to area* the area's
  rotated bounding box plus ¼ of its longer side. The mini-map block sets it before drawing; don't add a second transform.
- **Screen → view:** `screen_to_view()` is the only cursor px → main-view px map: `tracking_region()` fitted with one scale,
  centred (letterbox bars), cached in `view_scale`/`view_offset`. The trail, its first point and the main grid (`view_rect()`) use it.
  Any region change must call `set_view()`; it refits and moves the trail. Never scale x and y separately.
- **Tracking region:** `region_mode` (0 Full screen, 1 osu! game box, 2 osu! playfield) + `region_values` = [H pos %, V pos %,
  H scale %, V scale %, pen sensitivity], lazer's Screen scaling semantics. `tracking_region()` holds lazer's maths (box, 0.8 4:3
  playfield 8 osu!px lower, sensitivity about the monitor centre). The mini-map maps its corners through `screen_to_tablet()`.
- **Settings panel:** three 220-px columns at x 40/290/540, rows at y 64/432. Row 2 is Active Area (columns 1-2) and Tracking
  region (column 3); the panel has no free slot left.
  Click rects are the ones the same frame's draw calls returned (`draw_checkbox` includes the label). Never hard-code one.
- **Window:** read the handle with `window_handle()`. `set_mode` (borderless toggle) keeps the HWND but drops
  `HWND_TOPMOST`, so `set_borderless()` re-runs `apply_always_on_top()`. The borderless drag moves the window from the
  sampled `mouse_x/mouse_y`. Alt 1/2/3 and the OBS checkboxes share `set_borderless()` / `toggle_overlay_mode()`.
- **Presets:** new keys are optional and default off when missing (`always_on_top`, `minimap_zoom`; `region_mode` + the
  `region_*` / `pen_sensitivity` numbers → Full screen 50/50/100/100/1). Never rename old keys.
