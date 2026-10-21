# -*- mode: python ; coding: utf-8 -*-
# One-file release build. Run build.bat, or from a clean venv holding only pygame + pyinstaller:
#   pyinstaller --clean --noconfirm CursorTracker.spec
import os

# Stdlib and pygame modules the app never imports; keeps them (and their DLLs) out of the exe
EXCLUDES = [
    'pygame.mixer', 'pygame.mixer_music', 'pygame._sdl2', 'pygame.freetype', 'pygame._freetype',
    'pygame.ftfont', 'pygame.midi', 'pygame.pypm', 'pygame.camera', 'pygame._camera',
    'pygame._camera_opencv', 'pygame._camera_vidcapture', 'pygame.surfarray', 'pygame.sndarray',
    'pygame.examples', 'pygame.tests', 'pygame.docs', 'pygame.macosx',
    'pkg_resources', 'setuptools', 'numpy', 'PIL',
    'asyncio', 'concurrent', 'multiprocessing', 'email', 'http', 'xml', 'xmlrpc', 'pyexpat',
    'unittest', 'doctest', 'pydoc', 'pydoc_data', 'sqlite3', 'ssl', '_ssl', '_hashlib',
    '_lzma', '_bz2', '_decimal', 'unicodedata', 'tkinter.tix', 'turtle',
    # only reached through lazy imports this app never triggers (checked against a live run's sys.modules)
    'decimal', '_pydecimal', 'fractions', 'statistics', 'tarfile', 'gzip', 'bz2', 'lzma', 'pickle',
    '_compat_pickle', 'logging', 'pprint', 'dataclasses', 'tracemalloc', 'importlib.metadata',
    'importlib.resources', 'datetime', '_pydatetime', 'calendar', '_strptime', 'csv', 'quopri',
    'stringprep', 'py_compile',
]

# pygame's hook copies every DLL in its folder; these serve only audio, MIDI and JPEG/TIFF/WebP.
# ucrtbase and the api-ms-win-* stubs ship with Windows 10+.
DROP_BINARIES = {
    'sdl2_mixer.dll', 'libmodplug-1.dll', 'libogg-0.dll', 'libopus-0.dll', 'libopusfile-0.dll',
    'portmidi.dll', 'freetype.dll', 'libjpeg-9.dll', 'libtiff-5.dll', 'libwebp-7.dll', 'ucrtbase.dll',
}

def keep_binary(dest, src):
    name = os.path.basename(dest).lower()
    if name in DROP_BINARIES or name.startswith('api-ms-win-'):
        return False
    # pygame's hook also puts its DLLs at the top level; the copies under pygame/ are the ones loaded
    return not (os.path.dirname(dest) == '' and os.path.basename(os.path.dirname(src)).lower() == 'pygame')

# Tcl/Tk parts the dialogs never load: time zones, translations, demos, sample images
DROP_DATA_PREFIXES = (
    '_tcl_data/tzdata/', '_tcl_data/msgs/', '_tk_data/msgs/', '_tk_data/demos/', '_tk_data/images/',
)

a = Analysis(
    ['cursortracker.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('Configurations', 'Configurations'),
        ('cursor_logo.png', '.'),
        ('cursor_logo.ico', '.'),
        ('OpenTabletDriver.CustomDaemon.exe', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)
a.binaries = [b for b in a.binaries if keep_binary(b[0], b[1])]
a.datas = [d for d in a.datas if not d[0].replace('\\', '/').startswith(DROP_DATA_PREFIXES)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('X utf8', None, 'OPTION')],  # UTF-8 mode, so redirected -console output can't crash on CJK locales
    name='CursorTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # the app hides the console itself unless run with -console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['cursor_logo.ico'],
)
