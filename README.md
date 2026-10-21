# Simple Cursor Tracker

A small Windows overlay that draws your pen or mouse movement as a fading trail, with a mini-map of your tablet's active area. It's made for **OpenTabletDriver** users who want to show their cursor movement on stream (osu!, drawing, tutorials).

![Simple Cursor Tracker running borderless over an osu! editor](docs/demo.gif)

**[⬇ Download the latest release](https://github.com/Kanorin-chan/Simple-Cursor-Tracker/releases/latest)** · Windows only

---

## What it does

- **Live cursor trail.** Your primary monitor is scaled into an 800×600 window at its real proportions, with bars where the shapes differ, and the cursor leaves a smoothed trail that fades out. For osu!, the window can show only the game's box or the playfield (see [Tracking region](#tracking-region)). The cursor is read about 1000 times a second, so fast strokes keep their shape even though the window draws at 60 fps.
- **Tablet mini-map.** It shows the full tablet surface at its real proportions, your active area exactly as OTD maps it (position, size, rotation and display area), and where the pen is. It can also zoom to your active area, so a small area isn't a speck.
- **Automatic tablet detection.** On launch it briefly runs a bundled OpenTabletDriver daemon to identify your tablet. It then reads your area from OTD's `Settings.json` and the tablet's physical size from the bundled configuration files.
- **OBS-friendly modes.** You can switch to a borderless window that you drag to move, keep it always on top, and hide the UI, or the UI and the mini-map, so a window capture shows only the trail.
- **Customisable.** You can change the cursor, trail, active-area and background colours (hex or colour picker), the trail length, follow speed and thickness, and the grids. You can save and load presets as JSON.

## Quick start

1. Download `CursorTracker.exe` from the latest release. It's a single file (about 11 MB), with nothing to extract.
2. Plug in your tablet.
3. Run `CursorTracker.exe`. On first launch it asks **which OTD `Settings.json` to use**. Choose **Yes** to use the default `%LocalAppData%\OpenTabletDriver\Settings.json`. The app remembers your choice. It starts with the default look until you save a preset.
4. Move your pen. The trail appears in the main window and the dot moves on the mini-map.

Run `CursorTracker.exe -console` to keep the console open and see the detection log.

## Using it with OBS

Press **Alt** in the tracker window to open the overlay menu, then press a number:

| Key | Effect |
|---|---|
| `1` | Toggle a borderless window (no title bar) |
| `2` | Hide the UI and keep the mini-map. Press again to show it. |
| `3` | Hide the UI and the mini-map. Press again to show them. |

The number keys only work while the Alt menu is open. Pressing Alt again closes the menu.

The **OBS** section of the Settings panel has the same three toggles, plus **Always on top**. In borderless mode, drag any empty part of the main view to move the window (not the Settings button or the mini-map). With the UI hidden, the Settings button still works where it was, in the bottom-left corner.

In OBS, add a **Window Capture** of *Simple Cursor Tracking*. To remove the background, set a solid background colour in Settings (for example pure green `#00FF00`) and add a **Chroma Key** filter.

## Settings panel

Click **Settings** in the bottom-left corner to open the panel. **Close** is at the bottom right, beside the file buttons.

| Section | Options |
|---|---|
| Colors | Cursor, trail, area (the active-area outline) and background. Type a hex value or click a swatch to open the picker. **Tab** applies what you typed and moves to the next box (the area fields too, once unlocked). |
| Trail | Cursor trail on/off, fade on/off, main-window grid, length (shown in ms: 67–817, default 233), follow speed (0.1–1.0; higher follows the cursor more tightly, lower is smoother but lags more), thickness (1–10) |
| Minimap | Show/hide the mini-map, its grid, **Zoom to area** (frames your active area instead of the whole tablet), area outline thickness (1–5) |
| OBS | Borderless, Always on top, Hide UI, Hide UI + minimap. The same states as the Alt menu. |
| Active Area (mm) | Width, height, X/Y (the area's centre, as in OTD) and rotation, read from OTD. Locked by default: click the section 3 times within 3 seconds to edit. Edits change only the mini-map, not OTD, and reset to OTD's values on the next launch. |
| Tracking region | What the main window shows: Full screen, osu! game box or osu! playfield. Below that are osu!lazer's position and scale (%) and Pen sensitivity (x). See [Tracking region](#tracking-region). |
| File | **Save** writes a preset JSON, **Load** opens one, **Reset** restores the defaults (except Borderless and Hide UI). Presets also keep Always on top, Zoom to area and the tracking region. Older presets load with the first two off and Full screen. |

## Tracking region

The **Tracking region** section of the Settings panel picks which part of your primary monitor the main window shows. One scale is used for both directions, so a circle stays a circle, and the spare space becomes bars in the background colour.

| Mode | The main window shows |
|---|---|
| Full screen | The whole primary monitor |
| osu! game box | The box osu!lazer draws in when its Screen scaling is on |
| osu! playfield | The osu! standard playfield inside that box, adjusted for Pen sensitivity |

Click the right half of the mode box for the next mode, and the left half for the previous one. In the osu! modes, the mini-map draws the region on your tablet as a dashed orange outline, which is the part of the tablet you really play on.

Copy the numbers from osu!lazer:

| Tracker field | osu!lazer setting |
|---|---|
| Position (left box, right box) | Settings → Graphics → Layout → Screen scaling: **Horizontal position**, **Vertical position** (50% = centred) |
| Scale (left box, right box) | The same place: **Horizontal scale**, **Vertical scale** (20–100%). With Screen scaling **Off**, use 100% and 100%. |
| `x` box beside the mode | Settings → Input → Tablet (External) → **Pen sensitivity** (lazer 2026.518.0 and newer). Used in playfield mode only. |

Every Screen scaling mode except Off (Everything, Excluding overlays, Gameplay) puts gameplay in the same box. The tracker works the region out the way lazer's source does:

- **Game box:** width = horizontal scale × screen width, left edge = horizontal position × (screen width − box width). The same applies vertically.
- **Playfield:** 80% of the box, fitted to 4:3 and centred, then moved down by 8/512 of its width. lazer does this to line gameplay up with storyboards.
- **Pen sensitivity** puts the game cursor that many times further from the monitor's centre than the Windows cursor. The Windows cursor reaches the playfield's edges from a box 1/sensitivity its size around the centre, so that's the box the tracker shows.

For example, a 3840×2160 monitor with 50 / 50 / 66 / 76 % and sensitivity 1.1 gives a game box of 2534×1642 px at (653, 259) and a playfield of 1751×1313 px at (1044, 451). The cursor covers that playfield from 1592×1194 px at (1124, 508), which on a 28.5×24.7 mm OTD area is 11.8×13.7 mm of tablet.

## Files it creates

These are written next to the executable (or next to `cursortracker.py` when you run from source):

| File | Holds |
|---|---|
| `settings_config.json` | The path to your OpenTabletDriver `Settings.json` |
| `last_settings_path.json` | The last cursor preset you saved or loaded. It loads automatically on the next launch. |
| `cursor_settings.json` | The default name for a saved preset. You can save it anywhere. |

## Run from source

Requires Windows and Python 3.12 (the version it was tested on).

```bash
pip install -r requirements.txt
python cursortracker.py
```

The only dependency is pygame. Dialogs use tkinter, which ships with Python.

### Build the executable

Run `build.bat`. The first time, it creates a `.buildenv` virtual environment with only pygame and PyInstaller. It then builds `dist\CursorTracker.exe` (about 11 MB) from `CursorTracker.spec`.

The console is hidden at runtime unless you pass `-console`.

### Rebuild the detector daemon

`OpenTabletDriver.CustomDaemon.exe` is the stock OpenTabletDriver daemon with its single-instance name and RPC pipe renamed, so it runs beside your real OTD without either one seeing the other. To rebuild it from a newer OTD (needs the .NET 8 or later SDK):

1. Check out an OTD `0.6.x` release tag.
2. In `OpenTabletDriver.Daemon/Program.cs`, change `new Instance("OpenTabletDriver.Daemon")` and `new RpcHost<DriverDaemon>("OpenTabletDriver.Daemon")` to use `"OpenTabletDriver.Daemon.CustomDaemon"`.
3. In `OpenTabletDriver.Daemon/OpenTabletDriver.Daemon.csproj`, add `<AssemblyName>OpenTabletDriver.CustomDaemon</AssemblyName>` under `<OutputType>`.
4. Run `dotnet publish OpenTabletDriver.Daemon/OpenTabletDriver.Daemon.csproj -c Release -r win-x64 --no-self-contained -p:PublishSingleFile=true -p:DebugType=none -o out`.
5. Copy `out\OpenTabletDriver.CustomDaemon.exe` here, and replace `Configurations/` with the tag's `OpenTabletDriver.Configurations/Configurations`.

## Known issues

- **The trail can't show cursor updates faster than about 1000 per second.** A tablet or filter that outputs more often is sampled down to that.
- **The mini-map dot can be off when OTD's display area is on a monitor with different Windows scaling from your primary.** The app sees that monitor's cursor positions scaled.
- **The osu! tracking regions assume osu!lazer runs fullscreen or borderless on your primary monitor.** In a window, or on another monitor, the region is in the wrong place.
- **Pen sensitivity only counts if lazer applies it to your tablet.** lazer applies it to input that reaches its pen handler. That covers Windows Ink and, according to lazer's notes, absolute mouse input while High precision mouse is on. This hasn't been checked with OTD's Absolute mode. If the osu! cursor sits exactly on the Windows cursor, enter 1.
- **The trail isn't cut off at the region's edge.** When the cursor leaves the region, the trail is drawn in the bars or off the window.

## Troubleshooting

- **Wrong tablet or no tablet detected**: if the detector finds nothing within about 3 seconds, the app uses the first tablet in your OTD `Settings.json`. Plug the tablet in before you launch, and run with `-console` to see the detector output.
- **Wrong tablet size on the mini-map**: your model may be missing from `Configurations/`. The app asks you to pick a similar model.
- **Trail feels laggy**: raise *Follow speed* toward 1.0, or shorten the trail.

## Credits

- Tablet configuration files and the bundled detector daemon (`OpenTabletDriver.CustomDaemon.exe`, built from OpenTabletDriver 0.6.7) come from [OpenTabletDriver](https://github.com/OpenTabletDriver/OpenTabletDriver), licensed under **LGPL-3.0**.
- Built with [pygame](https://www.pygame.org/).
