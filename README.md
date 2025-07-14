# Cursor Tracker 
 
A Python-based cursor tracking tool designed for OpenTabletDriver users. This application provides real-time cursor visualization with customizable trails, colors, and tablet area mapping. 
 
## Features 
 
- **Real-time cursor tracking** with smooth movement visualization 
- **Customizable cursor trail** with fade effects and adjustable length 
- **Color customization** for cursor, trail, and background 
- **Tablet area mapping** with active area visualization 
- **Mini-map display** showing full tablet area and cursor position 
- **Settings persistence** - save and load your preferences 
- **OBS overlay support** with borderless window options 
- **OpenTabletDriver integration** - automatically detects tablet configurations 
 
## Installation 
 
### Prerequisites 
- Python 3.7+ 
- OpenTabletDriver (optional, for tablet configuration detection) 
 
### Dependencies 
```bash 
pip install pygame pyautogui numpy 
``` 
 
### Building the Executable 
```bash 
# Install PyInstaller 
pip install pyinstaller 
 
# Build executable with configurations 
pyinstaller --onefile --console --add-data "Configurations;Configurations" --name "CursorTracker" test4.py 
``` 
 
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
python test4.py 
``` 
 
## License 
 
This project is open source. The tablet configuration files are sourced from [OpenTabletDriver](https://github.com/OpenTabletDriver/OpenTabletDriver) under LGPL-3.0 license. 
 
## Credits 
 
- **Tablet Configurations**: [OpenTabletDriver](https://github.com/OpenTabletDriver/OpenTabletDriver) - Open source, cross-platform tablet driver 
- **Python Libraries**: pygame, pyautogui, numpy 
