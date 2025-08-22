# Cursor Tracker – Python Cursor Tracking Tool for Tablets & OBS

Cursor Tracker is a Python-based desktop utility for **real-time cursor visualization**, designed for **OpenTabletDriver** users.  
It features **customizable trails, colors, tablet area mapping, and OBS overlay support**, making it perfect for **digital artists, streamers, and educators**.  

With automatic tablet detection and full OpenTabletDriver integration, setup is simple—just run and start tracking!
 
## Features 
 
- **Real-time cursor tracking** with smooth movement visualization 
- **Customizable cursor trail** with fade effects and adjustable length 
- **Color customization** for cursor, trail, and background 
- **Tablet area mapping** with active area visualization 
- **Mini-map display** showing full tablet area and cursor position 
- **Settings persistence** - save and load your preferences 
- **OBS overlay support** with borderless window options 
- **OpenTabletDriver integration** - automatically detects tablet configurations 
- **Automated tablet detection** using a custom `opentabletdriver.daemon.exe` or `opentabletdriver.customdaemon.exe` (no manual selection required for most tablets; included in the install package)

## Installation 
 
### Prerequisites 
- Python 3.7+ 
- OpenTabletDriver (optional, for tablet configuration detection) 
- **The custom `opentabletdriver.daemon.exe` or `opentabletdriver.customdaemon.exe` is already included in the install package. You do not need to manually place it beside the executable.**
 
### Dependencies 
```bash 
pip install pygame pyautogui numpy 
``` 
 
### Building the Executable 
```bash 
# Install PyInstaller 
pip install pyinstaller 
 
# Build executable with configurations 
pyinstaller --onefile --console ^
--add-data "Configurations;Configurations" ^
--add-data "cursor_logo.png;." ^
--add-data "cursor_logo.ico;." ^
--add-data "opentabletdriver.customdaemon.exe;." ^
--name "CursorTracker" cursortracker.py
``` 

## Use Cases
- 🎨 Digital artists who want to visualize their pen movement
- 🎥 Streamers who want cursor trails in OBS overlays
- 🖱️ Developers testing cursor & input tracking
- 📊 Educators making tutorials with live cursor visualization

## Usage 
 
### Running the Application 
 
**Normal mode (hidden console):** 
```bash 
CursorTracker.exe 
``` 
 
**Debug mode (visible console):** 
```bash 
CursorTracker.exe -console 
``` 
 
### Tablet Detection (Automation)

- The application now features **automatic tablet detection** using a custom `opentabletdriver.daemon.exe` or `opentabletdriver.customdaemon.exe`.
- **The custom daemon executable is included in the install package. No manual placement is required.**
- When you launch the app, it will attempt to detect your connected tablet automatically and select the correct configuration.
- If your tablet is not detected, you will be prompted to select a similar configuration manually.
- This automation reduces setup time and improves user experience for most OpenTabletDriver-compatible tablets.

### Controls 
 
- **Settings Button**: Opens the settings panel 
- **Alt Key**: Toggle OBS overlay options 
- **1 Key**: Toggle borderless window mode 
- **2 Key**: Hide UI elements 
- **3 Key**: Hide UI + mini-map 
 
### Settings Panel 
 
The settings panel allows you to customize: 
 
- **Colors**: Cursor, trail, rectangle, and background colors 
- **Trail Settings**: Length, smoothness, thickness, and fade effects 
- **Grid Settings**: Enable/disable grids on main and mini displays 
- **Active Area**: Configure tablet active area dimensions 
- **File Operations**: Save, load, and reset settings 
 
## Configuration 
 
### Tablet Configuration Files 
 
This application includes tablet configuration files from [OpenTabletDriver](https://github.com/OpenTabletDriver/OpenTabletDriver). These files contain digitizer specifications for various tablet models and are used to automatically detect tablet dimensions. 

**Automatic Detection:**
- The app uses a custom `opentabletdriver.daemon.exe` or `opentabletdriver.customdaemon.exe` to detect your connected tablet and select the appropriate configuration automatically.
- The daemon is included in the install package.
- If detection fails, you can still manually select a configuration from the provided list.

**Credits:** Tablet configuration files are sourced from the [OpenTabletDriver project](https://github.com/OpenTabletDriver/OpenTabletDriver) under LGPL-3.0 license. 
 
### Settings Files 
 
The application creates several configuration files in the same directory as the executable: 
 
- `cursor_settings.json` - Main application settings 
- `settings_config.json` - OpenTabletDriver settings path 
- `last_settings_path.json` - Last used settings file path 
 
## Troubleshooting 
 
### Common Issues 
 
**Tablet not detected:** 
- Ensure OpenTabletDriver is running 
- Check that your tablet is properly connected 
- Verify OpenTabletDriver settings.json path is correct 
- The custom `opentabletdriver.daemon.exe` or `opentabletdriver.customdaemon.exe` is included in the install package.
 
**Configuration not found:** 
- The application will prompt you to select a similar tablet configuration 
- You can manually select from the available configurations 
 
**Performance issues:** 
- Reduce trail length in settings 
- Disable trail fade effects 
- Lower trail thickness 
 
## Building from Source 
 
### Development Setup 
```bash 
# Clone or download the source code 
# Install dependencies 
pip install pygame pyautogui numpy 
 
# Run the application 
python cursortracker.py 
``` 
 
## License 
 
This project is open source. The tablet configuration files are sourced from [OpenTabletDriver](https://github.com/OpenTabletDriver/OpenTabletDriver) under LGPL-3.0 license. 
 
## Credits 
 
- **Tablet Configurations**: [OpenTabletDriver](https://github.com/OpenTabletDriver/OpenTabletDriver) - Open source, cross-platform tablet driver 
- **Python Libraries**: pygame, pyautogui, numpy 
