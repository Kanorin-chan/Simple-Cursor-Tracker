@echo off
rem Release build: dist\CursorTracker.exe from a clean venv holding only pygame + PyInstaller.
rem Delete .buildenv to rebuild the venv from scratch.
setlocal
cd /d "%~dp0"
if not exist .buildenv\Scripts\python.exe (
    py -3.12 -m venv .buildenv 2>nul || python -m venv .buildenv || exit /b 1
    .buildenv\Scripts\python -m pip install --quiet pygame==2.6.1 pyinstaller==6.22.3 || exit /b 1
)
.buildenv\Scripts\pyinstaller --clean --noconfirm CursorTracker.spec || exit /b 1
for %%F in (dist\CursorTracker.exe) do echo Built %%~fF (%%~zF bytes)
