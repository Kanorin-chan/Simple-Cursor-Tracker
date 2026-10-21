import pygame
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
from tkinter import filedialog
import tkinter as tk
import time
import subprocess
import sys  # Make sure sys is imported first
import os
from tkinter import messagebox, filedialog
import math
import pygame.gfxdraw
import argparse
import threading
import re
from collections import deque

user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")

# System DPI awareness before any window exists; every coordinate below assumes physical pixels
user32.SetProcessDPIAware()

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]

kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]

_cursor_point = wintypes.POINT()

def get_cursor_pos():
    """Cursor position in physical screen pixels"""
    user32.GetCursorPos(ctypes.byref(_cursor_point))
    return _cursor_point.x, _cursor_point.y

# Cursor sampler thread: ~1 kHz so fast strokes keep their shape; the main loop drains it each frame
cursor_samples = deque(maxlen=2048)  # (perf_counter time, x, y), only when the cursor moved
sampler_stop = threading.Event()

def sample_cursor():
    """Poll the cursor every 1 ms (every 8 ms once it has been still for 0.5 s) and queue each change"""
    last, moved, due = None, 0.0, time.perf_counter()
    while not sampler_stop.is_set():
        now = time.perf_counter()
        pos = get_cursor_pos()
        if pos != last:
            last, moved = pos, now
            cursor_samples.append((now, *pos))
        # Fixed deadlines hold ~1 kHz; time.sleep uses a high-resolution timer since Python 3.11
        due = max(due + (0.001 if now - moved < 0.5 else 0.008), now)
        time.sleep(due - now)

def focus_tracker_window():
    """Bring the tracker window back to the front after a Tk dialog"""
    try:
        hwnd = user32.FindWindowW(None, "Simple Cursor Tracking")
        if hwnd:
            user32.SetForegroundWindow(hwnd)
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    except Exception:
        pass

# Now add the argument parsing
parser = argparse.ArgumentParser(description='Cursor Tracking Tool')
parser.add_argument('-console', action='store_true', help='Show console window')
args = parser.parse_args()

# Hide console if not using -console flag and running as exe
if not args.console and getattr(sys, 'frozen', False):
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

class OTDTabletDetector:
    def __init__(self, otd_path=None):
        self.daemon_process = None
        self.detected_tablets = []
        self.detected_tablet_info = None
        # If no path specified, use the directory where this script is located
        if otd_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.otd_path = script_dir
        else:
            self.otd_path = otd_path
        self.daemon_exe = os.path.join(self.otd_path, "opentabletdriver.customdaemon")
        if os.name == 'nt' and not self.daemon_exe.endswith('.exe'):
            self.daemon_exe += '.exe'

    def check_otd_installation(self) -> bool:
        """Check if OpenTabletDriver daemon is installed and accessible"""
        print(f"=== Diagnostic Information ===")
        print(f"Current working directory: {os.getcwd()}")
        print(f"OTD path: {self.otd_path}")
        print(f"Looking for daemon at: {self.daemon_exe}")
        try:
            files = os.listdir(self.otd_path)
            #Getting the List of file in current folder (DEBUG)
            #print(f"\nFiles in {self.otd_path}:")
            for file in sorted(files):
                full_path = os.path.join(self.otd_path, file)
                file_type = "DIR" if os.path.isdir(full_path) else "FILE"
                print(f"  {file_type}: {file}")
        except Exception as e:
            print(f"Error listing directory: {e}")
        if os.path.exists(self.daemon_exe):
            print(f"\n✓ Daemon executable found: {self.daemon_exe}")
            return True
        else:
            print(f"\n✗ No daemon executable found!")
            return False

    def is_daemon_running(self):
        snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == wintypes.HANDLE(-1).value:
            return False
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                if 'opentabletdriver.customdaemon' in entry.szExeFile.lower():
                    return True
                ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return False

    def start_daemon(self) -> bool:
        """Start the OpenTabletDriver daemon, in a new window if already running."""
        print("Starting OpenTabletDriver daemon...")
        print(f"Daemon path: {self.daemon_exe}")
        if self.is_daemon_running():
            print("Daemon is already running. Launching in simulation mode.")
            self.daemon_process = subprocess.Popen(
                [self.daemon_exe, "-simulation"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.otd_path,
                bufsize=1,
                universal_newlines=True
            )
        else:
            self.daemon_process = subprocess.Popen(
                [self.daemon_exe],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.otd_path,
                bufsize=1,
                universal_newlines=True
            )
        time.sleep(3)
        if self.daemon_process.poll() is None:
            print("✓ Daemon started successfully")
            return True
        else:
            print("✗ Daemon process terminated")
            stdout, _ = self.daemon_process.communicate()
            if stdout:
                print(f"Daemon output: {stdout}")
            return False

    def stop_daemon(self):
        """Stop the OpenTabletDriver daemon"""
        if self.daemon_process:
            try:
                self.daemon_process.terminate()
                self.daemon_process.wait(timeout=5)
                print("✓ Daemon stopped")
            except subprocess.TimeoutExpired:
                self.daemon_process.kill()
                print("✓ Daemon force-stopped")
            except Exception as e:
                print(f"Error stopping daemon: {e}")

    def run_detection_sequence(self):
        """Run the complete tablet detection sequence"""
        print("=== OpenTabletDriver Tablet Detection ===\n")
        if not self.check_otd_installation():
            print("✗ OpenTabletDriver daemon not found or not accessible")
            print("Please ensure OpenTabletDriver is installed and in PATH")
            return False
        print("✓ OpenTabletDriver daemon found")
        if not self.start_daemon():
            return False
        threading.Thread(target=self.print_daemon_output, daemon=True).start()
        time.sleep(10)  # Wait for some output (adjust as needed)
        print("\n=== Detected Tablets ===")
        if self.detected_tablets:
            for i, tablet in enumerate(self.detected_tablets, 1):
                print(f"  {i}. {tablet}")
        else:
            print("  No tablets detected yet (check daemon output above)")
        return True

    def print_daemon_output(self):
        """Prints output from the daemon process if available."""
        if self.daemon_process and self.daemon_process.stdout:
            for line in self.daemon_process.stdout:
                print(line, end="")

def main():
    """Main function to run the tablet detection"""
    detector = OTDTabletDetector()  # Will auto-detect script directory
    try:
        success = detector.run_detection_sequence()
        if success:
            print("\n✓ Detection completed successfully")
        else:
            print("\n✗ Detection failed")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        detector.stop_daemon()
        print("Cleanup completed")

# Initialize pygame
pygame.init()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

icon_path = resource_path("cursor_logo.png")
icon = pygame.image.load(icon_path)
pygame.display.set_icon(icon)

# Get screen size & set window size
SCREEN_WIDTH, SCREEN_HEIGHT = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
# Virtual-desktop top-left = OTD's display origin; read per-monitor aware, as other-DPI monitors appear scaled here
try:
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    _dpi_context = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
except AttributeError:
    _dpi_context = None
VIRTUAL_X, VIRTUAL_Y = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN
if _dpi_context:
    user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(_dpi_context))
WIN_WIDTH, WIN_HEIGHT = 800, 600
SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT = 200, 150  # Mini display

# Create main & small windows
screen = pygame.display.set_mode((WIN_WIDTH, WIN_HEIGHT))
small_screen = pygame.Surface((SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT), pygame.SRCALPHA)
pygame.display.set_caption("Simple Cursor Tracking")

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10

def window_handle():
    """pygame's window; read it fresh, set_mode may replace it"""
    return pygame.display.get_wm_info()["window"]

def apply_always_on_top():
    """Pin or unpin the window above others; set_mode drops the pin, so call it again after"""
    user32.SetWindowPos(window_handle(), HWND_TOPMOST if always_on_top else HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

# Settings file
SETTINGS_FILE = Path("cursor_settings.json")

cursor_rgb_values = [0, 255, 255]  # Default cyan
trail_rgb_values = [0, 255, 255]   # Default cyan

# Colors
BACKGROUND_COLOR = (20, 20, 20)
background_rgb_values = [20, 20, 20]  # For background color selector
cursor_color = (0, 255, 255)  # Default cursor color
trail_color = (0, 255, 255)  # Default trail color
GRID_COLOR = (50, 50, 50)  # Dark gray grid
BUTTON_COLOR = (30, 30, 30)  # Dark button color
BUTTON_HOVER_COLOR = (50, 50, 50)  # Hover color
BUTTON_TEXT_COLOR = (255, 255, 255)  # White text
MODAL_BG_COLOR = (30, 30, 30)  # Modal background

# Trail settings
trail = []
trail_times = []  # perf_counter time of each trail point
smooth_factor = 0.3
TRAIL_STEP = 3  # px between kept trail points; the newest point always follows the cursor

# Grid settings
GRID_SPACING = 20  # Grid spacing

# Tracking region: the part of the primary monitor the main view frames; osu! fields work like lazer's Screen scaling
REGION_MODES = ("Full screen", "osu! game box", "osu! playfield")
REGION_MODE_KEYS = ("full_screen", "osu_game_box", "osu_playfield")  # as saved in presets
REGION_KEYS = ("region_position_x", "region_position_y", "region_scale_x", "region_scale_y", "pen_sensitivity")
REGION_LABELS = ("Horizontal position", "Vertical position", "Horizontal scale", "Vertical scale", "Pen sensitivity")
REGION_DEFAULTS = (50, 50, 100, 100, 1.0)
REGION_LIMITS = ((0, 100), (0, 100), (20, 100), (20, 100), (0.1, 10))  # lazer's ranges
REGION_COLOR = (255, 170, 0)  # the region's outline on the mini-map
region_mode = 0
region_values = list(REGION_DEFAULTS)  # position % (50 = centred), scale %, pen sensitivity
region_inputs = [pygame.Rect(0, 0, 66, 22) for _ in range(5)]

def tracking_region():
    """(x, y, w, h) in cursor px: the primary monitor, lazer's Everything box on it, or the osu! playfield in that box"""
    if region_mode == 0:
        return 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT
    pos_x, pos_y, size_x, size_y, sensitivity = [min(max(v, low), high) for v, (low, high) in zip(region_values, REGION_LIMITS)]
    w, h = SCREEN_WIDTH * size_x / 100, SCREEN_HEIGHT * size_y / 100
    x, y = (SCREEN_WIDTH - w) * pos_x / 100, (SCREEN_HEIGHT - h) * pos_y / 100
    if region_mode == 1:
        return x, y, w, h
    # Playfield: 0.8 of the box fitted to 4:3, then 8 osu!px (of 512) lower
    pw = min(w, h * 4 / 3) * 0.8
    x, y, w, h = x + (w - pw) / 2, y + (h - pw * 3 / 4) / 2 + pw * 8 / 512, pw, pw * 3 / 4
    # Pen sensitivity scales the game cursor about the monitor centre, so the cursor covers 1/sensitivity of the playfield
    cx, cy = SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2
    return cx + (x - cx) / sensitivity, cy + (y - cy) / sensitivity, w / sensitivity, h / sensitivity

def region_fields():
    """Indices of the region fields the mode uses, in reading order"""
    return [4, 0, 1, 2, 3] if region_mode == 2 else [0, 1, 2, 3] if region_mode == 1 else []

def fit_view():
    """(scale, offset) fitting tracking_region() into the window: one scale for both axes, centred (letterboxed)"""
    x, y, w, h = tracking_region()
    scale = min(WIN_WIDTH / w, WIN_HEIGHT / h)
    return scale, ((WIN_WIDTH - w * scale) / 2 - x * scale, (WIN_HEIGHT - h * scale) / 2 - y * scale)

view_scale, view_offset = fit_view()

def screen_to_view(x, y):
    """Cursor pixel -> main-view pixel"""
    return x * view_scale + view_offset[0], y * view_scale + view_offset[1]

def view_rect():
    """The tracking region in the main view; outside it are the letterbox bars"""
    x, y, w, h = tracking_region()
    left, top = screen_to_view(x, y)
    return pygame.Rect(round(left), round(top), round(w * view_scale), round(h * view_scale)).clip(screen.get_rect())

def set_view():
    """Refit the view after a region change; the trail moves with it"""
    global view_scale, view_offset, prev_x, prev_y, trail_target
    old_scale, (old_x, old_y) = view_scale, view_offset
    view_scale, view_offset = fit_view()
    remap = lambda p: screen_to_view((p[0] - old_x) / old_scale, (p[1] - old_y) / old_scale)
    trail[:] = [remap(p) for p in trail]
    (prev_x, prev_y), trail_target = remap((prev_x, prev_y)), remap(trail_target)

# Get initial position
prev_x, prev_y = screen_to_view(*get_cursor_pos())
trail_target, smooth_time = (prev_x, prev_y), time.perf_counter()  # where the smoothed point heads, and its time

clock = pygame.time.Clock()
running = True
mini_visible = True  # Mini-screen toggle
settings_open = False  # Settings modal toggle
button_hover = False  # Button hover state

# Set transparency
small_screen.set_alpha(150)  # Semi-transparent

# Settings button setup
BUTTON_WIDTH, BUTTON_HEIGHT = 100, 40
button_rect = pygame.Rect(10, WIN_HEIGHT - BUTTON_HEIGHT - 10, BUTTON_WIDTH, BUTTON_HEIGHT)
minimap_rect = pygame.Rect(WIN_WIDTH - SMALL_WIN_WIDTH - 10, WIN_HEIGHT - SMALL_WIN_HEIGHT - 10, SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT)
window_drag = None  # Borderless drag: the grabbed point, from the window's top-left
font = pygame.font.Font(None, 24)

# Add these after your existing color definitions
INPUT_BOX_COLOR = (60, 60, 60)
INPUT_BOX_ACTIVE_COLOR = (80, 80, 80)
INPUT_BOX_HOVER_COLOR = (70, 70, 70)
INPUT_BOX_BORDER_COLOR = (100, 100, 100)
INPUT_BOX_ACTIVE_BORDER_COLOR = (150, 150, 150)
INPUT_BOX_ERROR_COLOR = (120, 60, 60)
INPUT_BOX_ERROR_BORDER_COLOR = (200, 100, 100)
INPUT_TEXT_COLOR = (255, 255, 255)
INPUT_PLACEHOLDER_COLOR = (150, 150, 150)
PREVIEW_SIZE = 40

# Input validation state
input_error = False
error_message = ""

# Active area unlock system
active_area_locked = True
active_area_unlock_clicks = 0
active_area_unlock_timer = 0
active_area_section = pygame.Rect(0, 0, 0, 0)  # Settings panel block, set where it's drawn; clicks here count toward unlocking

# Active area rectangle styling
active_area_color = (0, 255, 0)  # Default green color
active_area_thickness = 2  # Default thickness (integer 1-5)
active_area_rgb_values = [0, 255, 0]  # RGB values for active area color

# Color picker popup system
color_picker_open = False
color_picker_type = None  # "cursor" or "trail"
color_picker_temp_values = [0, 0, 0]  # Temporary RGB values while picking
color_picker_hue = 0
color_picker_saturation = 100
color_picker_value = 100
color_wheel_cache = [None, None]  # [value it was drawn for, surface]

# Color picker drag state
color_picker_dragging = False
color_picker_drag_type = None  # "wheel", "value_slider", "r_slider", "g_slider", "b_slider"

# Color preview rectangles for click detection
cursor_color_preview_rect = None
trail_color_preview_rect = None
active_area_color_preview_rect = None
background_color_preview_rect = None

background_hex_input_active = False

def show_message(message, duration=500):
    message_surface = font.render(message, True, BUTTON_TEXT_COLOR)
    message_rect = message_surface.get_rect(center=(WIN_WIDTH//2, WIN_HEIGHT - 100))
    # Boxed like the tooltips, so it stays readable over the Settings fields
    pygame.draw.rect(screen, (40, 40, 40), message_rect.inflate(20, 12))
    pygame.draw.rect(screen, (100, 100, 100), message_rect.inflate(20, 12), 1)
    screen.blit(message_surface, message_rect)
    pygame.display.update()
    pygame.time.wait(duration)

def hsv_to_rgb(h, s, v):
    """Convert HSV to RGB (h: 0-360, s: 0-100, v: 0-100)"""
    h = h / 60
    s = s / 100
    v = v / 100
    
    c = v * s
    x = c * (1 - abs((h % 2) - 1))
    m = v - c
    
    if h < 1:
        r, g, b = c, x, 0
    elif h < 2:
        r, g, b = x, c, 0
    elif h < 3:
        r, g, b = 0, c, x
    elif h < 4:
        r, g, b = 0, x, c
    elif h < 5:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    
    return [int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)]

def rgb_to_hsv(r, g, b):
    """Convert RGB to HSV (returns h: 0-360, s: 0-100, v: 0-100)"""
    r, g, b = r / 255, g / 255, b / 255
    cmax = max(r, g, b)
    cmin = min(r, g, b)
    diff = cmax - cmin
    
    if diff == 0:
        h = 0
    elif cmax == r:
        h = (60 * ((g - b) / diff) + 360) % 360
    elif cmax == g:
        h = (60 * ((b - r) / diff) + 120) % 360
    else:
        h = (60 * ((r - g) / diff) + 240) % 360
    
    s = 0 if cmax == 0 else (diff / cmax) * 100
    v = cmax * 100
    
    return h, s, v

def rgb_to_hex(r, g, b):
    """Convert RGB to hex string"""
    return f"#{r:02x}{g:02x}{b:02x}".upper()

def draw_color_picker_popup():
    """Draw the color picker popup"""
    global color_picker_temp_values
    
    # Popup dimensions and position
    popup_width, popup_height = 400, 350
    popup_x = (WIN_WIDTH - popup_width) // 2
    popup_y = (WIN_HEIGHT - popup_height) // 2
    
    # Draw dark overlay
    overlay = pygame.Surface((WIN_WIDTH, WIN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 128))
    screen.blit(overlay, (0, 0))
    
    # Draw popup background
    popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)
    pygame.draw.rect(screen, (50, 50, 50), popup_rect)
    pygame.draw.rect(screen, (100, 100, 100), popup_rect, 2)
    
    # Title
    picker_name = {"active_area": "Area"}.get(color_picker_type, (color_picker_type or "Color").title())
    title_text = f"{picker_name} Color Picker"
    title_surface = font.render(title_text, True, BUTTON_TEXT_COLOR)
    title_rect = title_surface.get_rect(centerx=popup_x + popup_width//2, y=popup_y + 10)
    screen.blit(title_surface, title_rect)
    
    # Color wheel area (simplified as a gradient circle)
    wheel_center_x = popup_x + 120
    wheel_center_y = popup_y + 120
    wheel_radius = 80
    
    # Draw color wheel (simplified version), re-rendered only when the value changes
    if color_wheel_cache[0] != color_picker_value:
        wheel_surface = pygame.Surface((wheel_radius * 2 + 2, wheel_radius * 2 + 2), pygame.SRCALPHA)
        for angle in range(0, 360, 5):
            for radius in range(0, wheel_radius, 2):
                h = angle
                s = (radius / wheel_radius) * 100
                v = color_picker_value
                rgb = hsv_to_rgb(h, s, v)

                x = wheel_radius + 1 + int(radius * math.cos(math.radians(angle)))
                y = wheel_radius + 1 + int(radius * math.sin(math.radians(angle)))
                pygame.draw.circle(wheel_surface, rgb, (x, y), 1)
        color_wheel_cache[:] = [color_picker_value, wheel_surface]
    screen.blit(color_wheel_cache[1], (wheel_center_x - wheel_radius - 1, wheel_center_y - wheel_radius - 1))

    # Draw wheel border
    pygame.draw.circle(screen, (200, 200, 200), (wheel_center_x, wheel_center_y), wheel_radius, 2)
    
    # Draw current selection indicator on wheel
    indicator_x = wheel_center_x + int((color_picker_saturation / 100) * wheel_radius * math.cos(math.radians(color_picker_hue)))
    indicator_y = wheel_center_y + int((color_picker_saturation / 100) * wheel_radius * math.sin(math.radians(color_picker_hue)))
    
    # Use different colors for drag state
    if color_picker_dragging and color_picker_drag_type == "wheel":
        pygame.draw.circle(screen, (255, 255, 0), (indicator_x, indicator_y), 6)  # Yellow when dragging
        pygame.draw.circle(screen, (0, 0, 0), (indicator_x, indicator_y), 6, 2)
    else:
        pygame.draw.circle(screen, (255, 255, 255), (indicator_x, indicator_y), 4)
        pygame.draw.circle(screen, (0, 0, 0), (indicator_x, indicator_y), 4, 1)
    
    # Value slider (right side of wheel)
    slider_x = wheel_center_x + wheel_radius + 20
    slider_y = wheel_center_y - wheel_radius
    slider_width = 20
    slider_height = wheel_radius * 2
    
    # Draw value slider background
    for i in range(slider_height):
        v = (slider_height - i) / slider_height * 100
        rgb = hsv_to_rgb(color_picker_hue, color_picker_saturation, v)
        y = slider_y + i
        pygame.draw.line(screen, rgb, (slider_x, y), (slider_x + slider_width, y))
    
    # Draw value slider border
    pygame.draw.rect(screen, (200, 200, 200), (slider_x, slider_y, slider_width, slider_height), 2)
    
    # Draw value slider indicator
    value_y = slider_y + slider_height - int((color_picker_value / 100) * slider_height)
    if color_picker_dragging and color_picker_drag_type == "value_slider":
        pygame.draw.rect(screen, (255, 255, 0), (slider_x - 3, value_y - 3, slider_width + 6, 6))  # Yellow when dragging
        pygame.draw.rect(screen, (0, 0, 0), (slider_x - 3, value_y - 3, slider_width + 6, 6), 1)
    else:
        pygame.draw.rect(screen, (255, 255, 255), (slider_x - 2, value_y - 2, slider_width + 4, 4))
    
    # RGB sliders
    slider_start_x = popup_x + 20
    slider_start_y = popup_y + 220
    slider_width_long = popup_width - 40
    slider_height_small = 15
    
    # R slider
    r_slider_rect = pygame.Rect(slider_start_x, slider_start_y, slider_width_long, slider_height_small)
    pygame.draw.rect(screen, (80, 80, 80), r_slider_rect)
    r_pos = slider_start_x + (color_picker_temp_values[0] / 255) * slider_width_long
    if color_picker_dragging and color_picker_drag_type == "r_slider":
        pygame.draw.circle(screen, (255, 255, 0), (int(r_pos), slider_start_y + slider_height_small//2), 8)  # Yellow when dragging
        pygame.draw.circle(screen, (0, 0, 0), (int(r_pos), slider_start_y + slider_height_small//2), 8, 2)
    else:
        pygame.draw.circle(screen, (255, 0, 0), (int(r_pos), slider_start_y + slider_height_small//2), 6)
    r_label = font.render(f"R: {color_picker_temp_values[0]}", True, BUTTON_TEXT_COLOR)
    screen.blit(r_label, (slider_start_x, slider_start_y - 20))
    
    # G slider
    g_slider_rect = pygame.Rect(slider_start_x, slider_start_y + 30, slider_width_long, slider_height_small)
    pygame.draw.rect(screen, (80, 80, 80), g_slider_rect)
    g_pos = slider_start_x + (color_picker_temp_values[1] / 255) * slider_width_long
    if color_picker_dragging and color_picker_drag_type == "g_slider":
        pygame.draw.circle(screen, (255, 255, 0), (int(g_pos), slider_start_y + 30 + slider_height_small//2), 8)  # Yellow when dragging
        pygame.draw.circle(screen, (0, 0, 0), (int(g_pos), slider_start_y + 30 + slider_height_small//2), 8, 2)
    else:
        pygame.draw.circle(screen, (0, 255, 0), (int(g_pos), slider_start_y + 30 + slider_height_small//2), 6)
    g_label = font.render(f"G: {color_picker_temp_values[1]}", True, BUTTON_TEXT_COLOR)
    screen.blit(g_label, (slider_start_x, slider_start_y + 10))
    
    # B slider
    b_slider_rect = pygame.Rect(slider_start_x, slider_start_y + 60, slider_width_long, slider_height_small)
    pygame.draw.rect(screen, (80, 80, 80), b_slider_rect)
    b_pos = slider_start_x + (color_picker_temp_values[2] / 255) * slider_width_long
    if color_picker_dragging and color_picker_drag_type == "b_slider":
        pygame.draw.circle(screen, (255, 255, 0), (int(b_pos), slider_start_y + 60 + slider_height_small//2), 8)  # Yellow when dragging
        pygame.draw.circle(screen, (0, 0, 0), (int(b_pos), slider_start_y + 60 + slider_height_small//2), 8, 2)
    else:
        pygame.draw.circle(screen, (0, 0, 255), (int(b_pos), slider_start_y + 60 + slider_height_small//2), 6)
    b_label = font.render(f"B: {color_picker_temp_values[2]}", True, BUTTON_TEXT_COLOR)
    screen.blit(b_label, (slider_start_x, slider_start_y + 40))
    
    # Color preview
    preview_rect = pygame.Rect(popup_x + popup_width - 80, popup_y + 20, 60, 60)
    pygame.draw.rect(screen, color_picker_temp_values, preview_rect)
    pygame.draw.rect(screen, (200, 200, 200), preview_rect, 2)
    
    # Hex value display
    hex_value = rgb_to_hex(*color_picker_temp_values)
    hex_surface = font.render(hex_value, True, BUTTON_TEXT_COLOR)
    hex_rect = hex_surface.get_rect(centerx=popup_x + popup_width - 50, y=popup_y + 90)
    screen.blit(hex_surface, hex_rect)
    
    # Buttons
    apply_rect = pygame.Rect(popup_x + 20, popup_y + popup_height - 40, 80, 30)
    cancel_rect = pygame.Rect(popup_x + popup_width - 100, popup_y + popup_height - 40, 80, 30)
    
    pygame.draw.rect(screen, BUTTON_COLOR, apply_rect)
    pygame.draw.rect(screen, BUTTON_COLOR, cancel_rect)
    
    apply_text = font.render("Apply", True, BUTTON_TEXT_COLOR)
    cancel_text = font.render("Cancel", True, BUTTON_TEXT_COLOR)
    
    screen.blit(apply_text, (apply_rect.centerx - apply_text.get_width()//2, 
                             apply_rect.centery - apply_text.get_height()//2))
    screen.blit(cancel_text, (cancel_rect.centerx - cancel_text.get_width()//2, 
                              cancel_rect.centery - cancel_text.get_height()//2))
    
    return {
        'wheel_center': (wheel_center_x, wheel_center_y),
        'wheel_radius': wheel_radius,
        'value_slider': (slider_x, slider_y, slider_width, slider_height),
        'r_slider': r_slider_rect,
        'g_slider': g_slider_rect,
        'b_slider': b_slider_rect,
        'apply_button': apply_rect,
        'cancel_button': cancel_rect
    }

def update_color_in_realtime():
    """Update RGB colors in real-time as user types"""
    global cursor_color, trail_color, cursor_rgb_values, trail_rgb_values  # Add this line
    
    # Don't update if color picker is open (color picker handles its own updates)
    if color_picker_open:
        return
    
    if active_input is None:
        return
    
    # Handle hex inputs
    if active_input.endswith("_hex"):
        hex_str = input_text.strip().lstrip('#')
        if len(hex_str) == 6:
            try:
                r = int(hex_str[0:2], 16)
                g = int(hex_str[2:4], 16)
                b = int(hex_str[4:6], 16)
                if active_input == "cursor_hex":
                    cursor_rgb_values = [r, g, b]
                    cursor_color = (r, g, b)
                elif active_input == "trail_hex":
                    trail_rgb_values = [r, g, b]
                    trail_color = (r, g, b)
                elif active_input == "rectangle_hex":
                    active_area_rgb_values = [r, g, b]
                    active_area_color = (r, g, b)
                elif active_input == "background_hex":
                    background_rgb_values = [r, g, b]
                    BACKGROUND_COLOR = (r, g, b)
            except ValueError:
                pass  # Keep current value if invalid
        return
    
    # Handle regular RGB inputs
    if active_input.startswith("cursor") and not active_input.endswith("_hex"):
        index = int(active_input.split("_")[1])
        try:
            if input_text.strip():
                value = int(input_text)
                # Clamp to 0-255 range
                clamped_value = max(0, min(255, value))
                cursor_rgb_values[index] = clamped_value
            else:
                cursor_rgb_values[index] = 0  # Default to 0 if empty
        except ValueError:
            pass  # Keep current value if invalid
        cursor_color = tuple(cursor_rgb_values)
    
    elif active_input.startswith("trail") and not active_input.endswith("_hex"):
        index = int(active_input.split("_")[1])
        try:
            if input_text.strip():
                value = int(input_text)
                # Clamp to 0-255 range
                clamped_value = max(0, min(255, value))
                trail_rgb_values[index] = clamped_value
            else:
                trail_rgb_values[index] = 0  # Default to 0 if empty
        except ValueError:
            pass  # Keep current value if invalid
        trail_color = tuple(trail_rgb_values)

#Cursor & Trail Color
cursor_rgb_inputs = [pygame.Rect(0, 0, 50, 30) for _ in range(3)]
trail_rgb_inputs = [pygame.Rect(0, 0, 50, 30) for _ in range(3)]
# Define active area variables before using them
active_area_x = 0
active_area_y = 0
active_area_width = 216  # Default fallback
active_area_height = 135  # Default fallback
active_area_rotation = 0
active_area_inputs = [pygame.Rect(0, 0, 80, 30) for _ in range(5)]  # Added for active area input boxes
active_area_values = [active_area_x, active_area_y, active_area_width, active_area_height, active_area_rotation]  # Ensure always defined
active_input = None
# Ensure these are lists of int, not restricted types
cursor_rgb_values = [int(c) for c in cursor_color]
trail_rgb_values = [int(c) for c in trail_color]
input_text = ""  # Add this to store temporary input text

# Ensure hex input state variables are always defined
cursor_hex_input_active = False
cursor_hex_input_text = ""
cursor_hex_input_rect = None

trail_hex_input_active = False
trail_hex_input_text = ""
trail_hex_input_rect = None

rectangle_hex_input_active = False
rectangle_hex_input_text = ""
rectangle_hex_input_rect = None

background_hex_input_active = False
background_hex_input_text = ""
background_hex_input_rect = None

# Backspace hold functionality
backspace_held = False
backspace_start_time = 0
backspace_repeat_delay = 500  # Initial delay in ms
backspace_repeat_interval = 50  # Repeat interval in ms

enable_trail = True  # Trail toggle
enable_main_grid = False  # Main screen grid toggle
enable_mini_grid = True  # Mini screen grid toggle
enable_mini_screen = True  # Mini screen toggle
trail_fade = True  # Trail fade toggle
always_on_top = False  # Window stays above others
minimap_zoom = False  # Mini-map frames the active area instead of the whole tablet

def get_configuration_path():
    """Get the path to the Configuration folder, whether running as script or exe"""
    if getattr(sys, 'frozen', False):
        # Running as exe
        base_path = sys._MEIPASS  # type: ignore
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, 'Configurations')

def scan_all_configurations():
    """Scan all configuration files and return available tablets"""
    config_path = get_configuration_path()
    available_tablets = []
    
    if not os.path.exists(config_path):
        print(f"Configuration folder not found: {config_path}")
        return available_tablets
    
    print("🔍 Scanning Configuration folder...")
    brand_folders = [f for f in os.listdir(config_path) if os.path.isdir(os.path.join(config_path, f))]
    
    for i, brand in enumerate(brand_folders):
        print(f"  📁 Scanning {brand}... ({i+1}/{len(brand_folders)})")
        brand_path = os.path.join(config_path, brand)
        model_files = [f for f in os.listdir(brand_path) if f.endswith('.json')]
        
        for model_file in model_files:
            model_name = model_file.replace('.json', '')
            full_name = f"{brand} {model_name}"
            available_tablets.append({
                'brand': brand,
                'model': model_name,
                'full_name': full_name,
                'path': os.path.join(brand_path, model_file)
            })
    
    print(f"✅ Found {len(available_tablets)} tablet configurations")
    return available_tablets

def find_known_brand(tablet_name, known_brands):
    """Find a known brand in the tablet name"""
    tablet_name_lower = tablet_name.lower()
    for brand in known_brands:
        if brand.lower() in tablet_name_lower:
            return brand
    return None

def try_find_config_file(brand, model):
    """Try to find a configuration file for the given brand and model"""
    config_path = get_configuration_path()
    config_file = os.path.join(config_path, brand, f'{model}.json')
    return config_file if os.path.exists(config_file) else None

def get_tablet_dimensions_from_config(tablet_name):
    """Enhanced tablet detection with multiple fallback strategies"""
    print(f"\n Searching for original tablet size section")
    print(f" ==========================================")
    print(f"\n🔍 Detecting tablet: '{tablet_name}'")
    
    # Known brands list
    known_brands = [
        "Wacom", "Huion", "XP-Pen", "ViewSonic", "UGEE", "Parblo", 
        "Xencelabs", "One by Wacom", "Intuos", "Cintiq", "Bamboo",
        "Acepen", "Adesso", "Artisul", "FlooGoo", "Gaomon", "Genius", 
        "KENTING", "Lifetec", "Monoprice", "RobotPen", "Trust", "Turcom", 
        "UC-Logic", "VEIKK", "Waltop", "XenceLabs", "XENX"
    ]
    
    # Step 1: Try to find known brand
    print("  📋 Step 1: Looking for known brand...")
    brand = find_known_brand(tablet_name, known_brands)
    if brand:
        print(f"    ✅ Found known brand: {brand}")
        model = tablet_name.replace(brand, "").strip()
        if model:
            print(f"    📝 Extracted model: {model}")
            config_file = try_find_config_file(brand, model)
            if config_file:
                print(f"    ✅ Found config file: {config_file}")
                return load_digitizer_dimensions(config_file)
            else:
                print(f"    ❌ No config file found for {brand} {model}")
        else:
            print(f"    ❌ No model extracted from '{tablet_name}'")
    else:
        print(f"    ❌ No known brand found in '{tablet_name}'")
    
    # Step 2: Word breakdown approach
    print("  🔧 Step 2: Trying word breakdown approach...")
    words = tablet_name.split()
    print(f"    📝 Breaking down: {words}")
    
    for i in range(len(words)):
        potential_brand = " ".join(words[:i+1])
        potential_model = " ".join(words[i+1:])
        
        if potential_model:  # Only try if we have both brand and model
            print(f"    🔍 Trying: Brand='{potential_brand}', Model='{potential_model}'")
            config_file = try_find_config_file(potential_brand, potential_model)
            if config_file:
                print(f"    ✅ Found config file: {config_file}")
                return load_digitizer_dimensions(config_file)
    
    print("    ❌ No configuration found with word breakdown")
    
    # Step 3: Scan all configurations and find best match
    print("  🔍 Step 3: Scanning all configurations...")
    available_tablets = scan_all_configurations()
    
    if available_tablets:
        print("  📋 Step 4: Showing tablet selection dialog...")
        selected_tablet = show_tablet_selection_dialog(tablet_name, available_tablets)
        if selected_tablet:
            print(f"    ✅ User selected: {selected_tablet['full_name']}")
            return load_digitizer_dimensions(selected_tablet['path'])
    
    print("    ❌ No tablet configuration found or selected")
    return None, None

def load_digitizer_dimensions(config_file):
    """Load digitizer dimensions from a configuration file"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Look for Specifications > Digitizer
        digitizer = None
        if 'Specifications' in config and 'Digitizer' in config['Specifications']:
            digitizer = config['Specifications']['Digitizer']
        elif 'Digitizer' in config:
            digitizer = config['Digitizer']
        
        if digitizer and 'Width' in digitizer and 'Height' in digitizer:
            print(f"    ✅ Found dimensions: {digitizer['Width']}x{digitizer['Height']} mm")
            return digitizer['Width'], digitizer['Height']
        else:
            print(f"    ❌ Digitizer dimensions not found in {config_file}")
            return None, None
    except Exception as e:
        print(f"    ❌ Failed to load config file {config_file}: {e}")
        return None, None

def show_tablet_selection_dialog(current_tablet_name, available_tablets):
    """Show a dialog for tablet selection"""
    root = tk.Tk()
    root.title("Tablet Configuration Selection")
    root.geometry("600x400")
    
    # Center the window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (600 // 2)
    y = (root.winfo_screenheight() // 2) - (400 // 2)
    root.geometry(f"600x400+{x}+{y}")
    
    # Make it modal
    root.transient()
    root.grab_set()
    
    # Create main frame
    main_frame = tk.Frame(root, padx=20, pady=20)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Title
    title_label = tk.Label(main_frame, text="Tablet Configuration Not Found", 
                          font=("Arial", 14, "bold"))
    title_label.pack(pady=(0, 10))
    
    # Current tablet info
    current_label = tk.Label(main_frame, 
                           text=f"Current tablet: {current_tablet_name}",
                           font=("Arial", 10))
    current_label.pack(pady=(0, 20))
    
    # Instructions
    instruction_label = tk.Label(main_frame, 
                               text="Please select the most similar tablet configuration:",
                               font=("Arial", 10))
    instruction_label.pack(pady=(0, 10))
    
    # Create listbox with scrollbar
    listbox_frame = tk.Frame(main_frame)
    listbox_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
    
    scrollbar = tk.Scrollbar(listbox_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, font=("Arial", 10))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=listbox.yview)
    
    # Populate listbox
    for tablet in available_tablets:
        listbox.insert(tk.END, tablet['full_name'])
    
    # Select first item by default
    if available_tablets:
        listbox.selection_set(0)
    
    selected_tablet = [None]  # Use list to store result
    
    def on_select():
        selection = listbox.curselection()
        if selection:
            index = selection[0]
            selected_tablet[0] = available_tablets[index]
        root.destroy()
    
    def on_cancel():
        root.destroy()
    
    # Buttons
    button_frame = tk.Frame(main_frame)
    button_frame.pack(fill=tk.X)
    
    select_button = tk.Button(button_frame, text="Select", command=on_select, 
                            font=("Arial", 10), width=10)
    select_button.pack(side=tk.RIGHT, padx=(10, 0))
    
    cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel, 
                            font=("Arial", 10), width=10)
    cancel_button.pack(side=tk.RIGHT)
    
    # Bind double-click
    listbox.bind('<Double-Button-1>', lambda e: on_select())
    
    # Focus and wait
    listbox.focus_set()
    root.wait_window()
    
    return selected_tablet[0]

def get_saved_settings_path():
    """Load the previously saved settings path from a config file."""
    if getattr(sys, 'frozen', False):
        # Running as exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    config_file = os.path.join(base_path, "settings_config.json")
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            saved_path = config.get('settings_path')
            if saved_path:
                print(f"Found saved settings path: {saved_path}")
            return saved_path
    except:
        print("No saved settings path found.")
        return None

def save_settings_path(path):
    """Save the selected settings path to a config file."""
    if getattr(sys, 'frozen', False):
        # Running as exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    config_file = os.path.join(base_path, "settings_config.json")
    try:
        with open(config_file, 'w') as f:
            json.dump({'settings_path': path}, f)
        print(f"Saved settings path: {path}")
    except Exception as e:
        print(f"Failed to save settings path: {e}")

def prompt_for_settings_selection():
    """Show dialog to select settings file or use default."""
    root = tk.Tk()
    root.withdraw()
    
    # Check if we have a saved path
    saved_path = get_saved_settings_path()
    if saved_path and os.path.isfile(saved_path):
        response = messagebox.askyesnocancel(
            "Settings File Selection",
            f"Previously used settings file:\n{saved_path}\n\nClick 'Yes' to use this file, 'No' to select a different file, or 'Cancel' to exit."
        )
        if response is None:  # Cancel
            print("User cancelled. Exiting.")
            exit(0)
        elif response:  # Yes: use saved path
            return saved_path
    
    # No saved path or user wants to select different file
    response = messagebox.askyesnocancel(
        "Settings File Selection",
        f"Default Settings.json location:\n{os.path.expandvars(r'%LocalAppData%/OpenTabletDriver/Settings.json')}\n\nClick 'Yes' to use default, 'No' to select a file, or 'Cancel' to exit."
    )
    if response is None:  # Cancel
        print("User cancelled. Exiting.")
        exit(0)
    elif response:  # Yes: use default
        default_path = os.path.expandvars(r"%LocalAppData%/OpenTabletDriver/Settings.json")
        if os.path.isfile(default_path):
            save_settings_path(default_path)
            return default_path
        else:
            print("Default settings file not found.")
            return None
    else:  # No: select file
        file_path = filedialog.askopenfilename(
            title="Select OpenTabletDriver Settings.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if file_path:
            save_settings_path(file_path)
            return file_path
        else:
            print("No file selected.")
            return None

def try_get_tablet_info(settings, target_tablet=None):
    # If a target_tablet is specified, look for it in Profiles
    if target_tablet:
        for profile in settings.get("Profiles", []):
            name = profile.get("Tablet") or profile.get("Name") or profile.get("Model") or "Unknown"
            if name == target_tablet:
                abs_mode = profile.get("AbsoluteModeSettings")
                if abs_mode and "Tablet" in abs_mode:
                    tab = abs_mode["Tablet"]
                    if all(key in tab for key in ["Width", "Height", "X", "Y"]):
                        area = [tab["X"], tab["Y"], tab["X"] + tab["Width"], tab["Y"] + tab["Height"]]
                        display = abs_mode.get("Display")
                        return name, area, display, tab
                        
                # Fallback: try Area/Display at profile level
                area = profile.get("Area")
                display = profile.get("Display")
                if area or display:
                    return name, area, display, None
    # Fallback: original logic
    for device in settings.get("Devices", []):
        area = device.get("Area")
        name = device.get("Tablet") or device.get("Name") or device.get("Model") or "Unknown"
        if area:
            return name, area, None, None
    for profile in settings.get("Profiles", []):
        name = profile.get("Tablet") or profile.get("Name") or profile.get("Model") or "Unknown"
        area = profile.get("Area")
        display = profile.get("Display")
        if area or display:
            return name, area, display, None
        abs_mode = profile.get("AbsoluteModeSettings")
        if abs_mode:
            abs_tablet = abs_mode.get("Tablet")
            abs_display = abs_mode.get("Display")
            if abs_tablet or abs_display:
                return name, None, abs_display, abs_tablet
        if name != "Unknown":
            return name, None, None, None
    return "Unknown", None, None, None

# Initialize variables
tablet_width = 216  # Default fallback
tablet_height = 135  # Default fallback
tablet_name = "Unknown"
display_width = None
display_height = None
display_x = None
display_y = None
# Active area from settings
active_area_x = 0
active_area_y = 0
active_area_width = 216  # Default fallback
active_area_height = 135  # Default fallback
active_area_rotation = 0

# Replace the settings loading logic with:
settings_path = prompt_for_settings_selection()

# Restore focus to Pygame window after initial settings selection
focus_tracker_window()

detector = OTDTabletDetector()
use_settings_json = False
found_tablet = False

if detector.check_otd_installation():
    if detector.start_daemon():
        timeout_seconds = 3
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if detector.daemon_process and detector.daemon_process.stdout:
                line = detector.daemon_process.stdout.readline()
                if line:
                    print(line, end="")
                    if "Found tablet" in line:
                        detector.detected_tablet_info = line.strip()
                        found_tablet = True
                        break
            else:
                time.sleep(0.1)

        detector.stop_daemon()

        if found_tablet:
            if detector.detected_tablet_info is not None:
                match = re.search(r"Found tablet '(.+)'", detector.detected_tablet_info)
            else:
                match = None
            print(f"Detected tablet info: {detector.detected_tablet_info}")
            if match:
                tablet_name = match.group(1)
                target_tablet = tablet_name

                print(f"Detected tablet: {tablet_name}")

                show_message(f"Tablet found: {tablet_name}", 2000)


                print(f"\nReading settings from: {settings_path}")

                if settings_path is None or not os.path.isfile(settings_path):
                    print("✗ No valid settings file found. Using default values.")
                    tablet_name = "Unknown"
                    tablet_width = 216
                    tablet_height = 135
                else:
                    try:
                        with open(settings_path, "r", encoding="utf-8") as f:
                            settings = json.load(f)

                        tablet_name, area, display, abs_tablet = try_get_tablet_info(settings, target_tablet=target_tablet)

                        # Update active_area_values from area or abs_tablet
                        if area:
                            tablet_width = area[2] - area[0]
                            tablet_height = area[3] - area[1]
                            print(f"Tablet area: {area}")
                            # Update active area values
                            active_area_x = area[0]
                            active_area_y = area[1]
                            active_area_width = tablet_width
                            active_area_height = tablet_height
                            active_area_values = [active_area_x, active_area_y, active_area_width, active_area_height]
                        elif abs_tablet:
                            tablet_width = abs_tablet.get("Width")
                            tablet_height = abs_tablet.get("Height")
                            print(f"Tablet (from AbsoluteModeSettings): {abs_tablet}")
                            # Update active area values
                            active_area_x = abs_tablet.get("X", 0)
                            active_area_y = abs_tablet.get("Y", 0)
                            active_area_width = abs_tablet.get("Width", 216)
                            active_area_height = abs_tablet.get("Height", 135)
                            active_area_rotation = abs_tablet.get("Rotation", 0)
                        else:
                            print("Tablet area not found, using default size.")
                            tablet_width = 216
                            tablet_height = 135

                        # Active area extract
                        active_area_found = False
                        
                        for profile in settings.get("Profiles", []):
                            if profile.get("Tablet") == target_tablet:
                                abs_mode = profile.get("AbsoluteModeSettings")
                                if abs_mode and "Tablet" in abs_mode:
                                    tab = abs_mode["Tablet"]
                                    if all(key in tab for key in ["Width", "Height", "X", "Y"]):
                                        
                                        active_area_found = True
                                        active_area_x = tab['X']
                                        active_area_y = tab['Y']
                                        active_area_width = tab['Width']
                                        active_area_height = tab['Height']
                                        active_area_rotation = tab.get('Rotation', 0)

                                        break
                        else:
                            print(f"Nyaa~ {target_tablet} not found in profiles (；´д｀)ゞ")

                        if not active_area_found:
                            print("Active area not found in settings.")

                        if display:
                            display_width = display.get("Width")
                            display_height = display.get("Height")
                            display_x, display_y = display.get("X"), display.get("Y")
                            print(f"Display width: {display_width}, height: {display_height}, centre: {display_x}, {display_y}")

                    except Exception as e:
                        print(f"Failed to read OpenTabletDriver area: {e}")
                        tablet_name = "Unknown"
                        tablet_width = 216
                        tablet_height = 135
            else:
                print("Could not extract tablet name. Fallback to settings.")
                use_settings_json = True
        else:
            print("No tablet detected within timeout. Fallback to settings.")
            use_settings_json = True
    else:
        print("Daemon failed to start. Fallback to settings.")
        use_settings_json = True
else:
    print("OTD daemon not found. Fallback to settings.")
    use_settings_json = True

if use_settings_json:
    print(f"Reading settings from: {settings_path}")

    if settings_path is None or not os.path.isfile(settings_path):
        print("✗ No valid settings file found. Using default values.")
        tablet_name = "Unknown"
        tablet_width = 216
        tablet_height = 135
    else:
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            
            tablet_name, area, display, abs_tablet = try_get_tablet_info(settings)

            if area:
                tablet_width = area[2] - area[0]
                tablet_height = area[3] - area[1]
                print(f"Tablet area: {area}")
            elif abs_tablet:
                tablet_width = abs_tablet.get("Width")
                tablet_height = abs_tablet.get("Height")
                print(f"Tablet (from AbsoluteModeSettings): {abs_tablet}")
                if all(key in abs_tablet for key in ["Width", "Height", "X", "Y"]):
                    active_area_x, active_area_y = abs_tablet["X"], abs_tablet["Y"]
                    active_area_width, active_area_height = abs_tablet["Width"], abs_tablet["Height"]
                    active_area_rotation = abs_tablet.get("Rotation", 0)
            else:
                print("Tablet area not found, using default size.")
                tablet_width = 216
                tablet_height = 135

            if display:
                display_width = display.get("Width")
                display_height = display.get("Height")
                display_x, display_y = display.get("X"), display.get("Y")
                print(f"Display width: {display_width}, height: {display_height}, centre: {display_x}, {display_y}")

        except Exception as e:
            print(f"Failed to read OpenTabletDriver area: {e}")
            tablet_name = "Unknown"
            tablet_width = 216
            tablet_height = 135

    # No tablet from the daemon: continue with the name Settings.json gave
    target_tablet = tablet_name

# After tablet_name is detected, add this logic:
print(f"\nFinal tablet model/name: {target_tablet}", flush=True)
# Separate brand and model
parts = target_tablet.split()
if len(parts) >= 2:
    brand = parts[0]
    model = ' '.join(parts[1:])
    print(f"Brand: {brand}, Model: {model}", flush=True)
    # Load dimensions from config
    tablet_width, tablet_height = get_tablet_dimensions_from_config(target_tablet)
    if tablet_width is None or tablet_height is None:
        print("Using default tablet size (216x135)")
        tablet_width, tablet_height = 216, 135
else:
    print(f"Tablet name '{target_tablet}' is not in expected 'Brand Model' format.")
    tablet_width, tablet_height = 216, 135

print(f"\n=== Final Data Display ===")
print(f"\nFinal tablet width: {tablet_width}, height: {tablet_height}", flush=True)
# OTD's display area as (centre x, centre y, width, height) in cursor pixels; X/Y count from the virtual-desktop top-left
if None in (display_x, display_y) or not (display_width and display_height):
    print("[HINT] Display area not found in settings. Mapping to the primary monitor.", flush=True)
    display_area = (SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2, SCREEN_WIDTH, SCREEN_HEIGHT)
else:
    display_area = (display_x + VIRTUAL_X, display_y + VIRTUAL_Y, display_width, display_height)
print(f"Final display area (centre x, centre y, width, height on screen): {display_area}", flush=True)

if tablet_width == 216 and tablet_height == 135:
    print("[HINT] Tablet area not found in settings. Using default tablet area (216x135).", flush=True)

# No area in Settings.json: OTD's default, the whole tablet
if (active_area_x, active_area_y, active_area_width, active_area_height) == (0, 0, 216, 135):
    print("[HINT] Active area is set to default (no settings found).", flush=True)
    active_area_x, active_area_y = tablet_width / 2, tablet_height / 2
    active_area_width, active_area_height = tablet_width, tablet_height

# Active Area Input Boxes - these now represent the ACTIVE area from settings
active_area_inputs = [pygame.Rect(0, 0, 80, 30) for _ in range(5)]
# OTD's convention: X/Y are the area's centre, rotation in degrees
active_area_values = [active_area_x, active_area_y, active_area_width, active_area_height, active_area_rotation]

print(f"Final Active area (centre x, centre y, width, height, rotation): {active_area_values}", flush=True)

#Trail Length Slider
SLIDER_COLOR = (80, 80, 80)
SLIDER_HOVER_COLOR = (100, 100, 100)
SLIDER_WIDTH = 200
SLIDER_HEIGHT = 10

trail_length_slider = pygame.Rect(0, 0, SLIDER_WIDTH, SLIDER_HEIGHT)
slider_grabbed = False
min_trail_length = 5
max_trail_length_limit = 50  # Maximum possible value
current_trail_length = 15    # Starting trail length

# Smoothness slider
smooth_factor_slider = pygame.Rect(0, 0, SLIDER_WIDTH, SLIDER_HEIGHT)
min_smooth = 0.1
max_smooth = 1.0
current_smooth = 0.3  # Default smoothness

# Trail thickness slider
trail_thickness_slider = pygame.Rect(0, 0, SLIDER_WIDTH, SLIDER_HEIGHT)
min_thickness = 1
max_thickness = 10
current_thickness = 2  # Default thickness

# Active-area outline thickness slider (1-5)
area_thickness_slider = pygame.Rect(0, 0, SLIDER_WIDTH, SLIDER_HEIGHT)

def screen_to_tablet(x, y):
    """Cursor pixel -> tablet mm, the inverse of OTD's AbsoluteOutputMode.CalculateTransformation.
    OTD: minus area centre, rotate by -Rotation, scale area to display, plus display centre."""
    area_x, area_y, area_w, area_h, rotation = active_area_values
    centre_x, centre_y, display_w, display_h = display_area
    u, v = (x - centre_x) * area_w / display_w, (y - centre_y) * area_h / display_h
    a = math.radians(rotation)
    return area_x + u * math.cos(a) - v * math.sin(a), area_y + u * math.sin(a) + v * math.cos(a)

minimap_view = (0, 0, tablet_width, tablet_height)  # (x, y, w, h) mm the mini-map frames: tablet, or area when zoomed

def tablet_to_minimap(mm_x, mm_y):
    """Tablet mm -> mini-map pixel: one scale for both axes, minimap_view centred (letterboxed)"""
    view_x, view_y, view_w, view_h = minimap_view
    scale = min(SMALL_WIN_WIDTH / view_w, SMALL_WIN_HEIGHT / view_h)
    return ((SMALL_WIN_WIDTH - view_w * scale) / 2 + (mm_x - view_x) * scale,
            (SMALL_WIN_HEIGHT - view_h * scale) / 2 + (mm_y - view_y) * scale)

def get_last_used_settings_path():
    """Load the path of the last used settings file."""
    if getattr(sys, 'frozen', False):
        # Running as exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    config_file = os.path.join(base_path, "last_settings_path.json")
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('last_settings_path')
    except:
        return None

def save_last_used_settings_path(filepath):
    """Save the path of the last used settings file."""
    if getattr(sys, 'frozen', False):
        # Running as exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    config_file = os.path.join(base_path, "last_settings_path.json")
    try:
        with open(config_file, 'w') as f:
            json.dump({'last_settings_path': filepath}, f)
    except Exception as e:
        print(f"Failed to save last settings path: {e}")

def save_settings():
    settings = {
        'cursor_color': cursor_rgb_values,
        'trail_color': trail_rgb_values,
        'trail_length': current_trail_length,
        'enable_trail': enable_trail,
        'trail_fade': trail_fade,
        'enable_main_grid': enable_main_grid,
        'enable_mini_grid': enable_mini_grid,
        'enable_mini_screen': enable_mini_screen,
        'smooth_factor': current_smooth,
        'trail_thickness': current_thickness,
        'active_area_left': active_area_values[0],
        'active_area_top': active_area_values[1],
        'active_area_width': active_area_values[2],
        'active_area_height': active_area_values[3],
        'active_area_rotation': active_area_values[4],
        'active_area_color': active_area_rgb_values,
        'active_area_thickness': active_area_thickness,
        'background_color': background_rgb_values,
        'always_on_top': always_on_top,
        'minimap_zoom': minimap_zoom,
        'region_mode': REGION_MODE_KEYS[region_mode],
        **dict(zip(REGION_KEYS, region_values))
    }

    # Show file dialog for save location
    root = tk.Tk()
    root.withdraw()
    
    # Use exe directory as default location
    if getattr(sys, 'frozen', False):
        # Running as exe
        default_dir = os.path.dirname(sys.executable)
    else:
        # Running as script
        default_dir = os.path.dirname(os.path.abspath(__file__))
    
    filepath = filedialog.asksaveasfilename(
        title="Save Cursor Settings",
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        initialdir=default_dir,
        initialfile="cursor_settings.json"
    )
    
    # Restore focus to Pygame window after dialog
    focus_tracker_window()

    if filepath:
        try:
            with open(filepath, 'w') as f:
                json.dump(settings, f, indent=2)
            print(f"Settings saved to: {filepath}")
            # Save this as the last used path
            save_last_used_settings_path(filepath)
            return True
        except Exception as e:
            print(f"Failed to save settings: {e}")
            return False
    else:
        print("Save cancelled by user.")
        return False

def load_settings(filepath=None, manual_load=False):
    global cursor_rgb_values, trail_rgb_values, current_trail_length
    global enable_trail, trail_fade, enable_main_grid, enable_mini_grid, enable_mini_screen
    global current_smooth, current_thickness, cursor_color, trail_color
    global active_area_values, active_area_rgb_values, active_area_color, active_area_thickness
    global background_rgb_values, BACKGROUND_COLOR, always_on_top, minimap_zoom, region_mode
    try:
        # If no filepath provided, check if it's manual load or automatic load
        if filepath is None:
            if manual_load:
                # Manual load: always show file dialog
                root = tk.Tk()
                root.withdraw()
                
                # Use exe directory as default location
                if getattr(sys, 'frozen', False):
                    # Running as exe
                    default_dir = os.path.dirname(sys.executable)
                else:
                    # Running as script
                    default_dir = os.path.dirname(os.path.abspath(__file__))
                
                filepath = filedialog.askopenfilename(
                    title="Load Cursor Settings",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                    initialdir=default_dir
                )
                
                # Restore focus to Pygame window after dialog
                focus_tracker_window()
            else:
                # Automatic load: only the last used file, otherwise keep the defaults silently
                last_path = get_last_used_settings_path()
                if not (last_path and os.path.isfile(last_path)):
                    print("No last used settings file. Using defaults.")
                    return False
                print(f"\nLoading last used settings: {last_path}")
                filepath = last_path

        if filepath and os.path.isfile(filepath):  # Only load if file was selected and exists
            with open(filepath, 'r') as f:
                settings = json.load(f)
                cursor_rgb_values = settings.get('cursor_color', cursor_rgb_values)
                trail_rgb_values = settings.get('trail_color', trail_rgb_values)
                current_trail_length = settings.get('trail_length', current_trail_length)
                enable_trail = settings.get('enable_trail', enable_trail)
                trail_fade = settings.get('trail_fade', trail_fade)
                enable_main_grid = settings.get('enable_main_grid', enable_main_grid)
                enable_mini_grid = settings.get('enable_mini_grid', enable_mini_grid)
                enable_mini_screen = settings.get('enable_mini_screen', enable_mini_screen)
                current_smooth = settings.get('smooth_factor', current_smooth)
                current_thickness = settings.get('trail_thickness', current_thickness)
                
                # Load active area values
                active_area_values[0] = settings.get('active_area_left', active_area_values[0])
                active_area_values[1] = settings.get('active_area_top', active_area_values[1])
                active_area_values[2] = settings.get('active_area_width', active_area_values[2])
                active_area_values[3] = settings.get('active_area_height', active_area_values[3])
                active_area_values[4] = settings.get('active_area_rotation', 0)  # older presets have none

                # Load active area styling
                active_area_rgb_values = settings.get('active_area_color', active_area_rgb_values)
                active_area_thickness = settings.get('active_area_thickness', active_area_thickness)
                
                # Load background color
                background_rgb_values = settings.get('background_color', background_rgb_values)
                BACKGROUND_COLOR = tuple(background_rgb_values)

                # Optional keys: older presets lack them, so they mean off
                always_on_top = settings.get('always_on_top', False)
                minimap_zoom = settings.get('minimap_zoom', False)
                apply_always_on_top()
                # Tracking region, optional too: missing = full screen and lazer's neutral values
                loaded_values = [float(settings.get(key, default)) for key, default in zip(REGION_KEYS, REGION_DEFAULTS)]
                mode = settings.get('region_mode')
                region_mode = REGION_MODE_KEYS.index(mode) if mode in REGION_MODE_KEYS else 0
                region_values[:] = loaded_values
                set_view()

                # Update colors
                cursor_color = tuple(cursor_rgb_values)
                trail_color = tuple(trail_rgb_values)
                active_area_color = tuple(active_area_rgb_values)
                # Update background color
                BACKGROUND_COLOR = tuple(background_rgb_values)
                print(f"Settings loaded from: {filepath}")
                # Save this as the last used path
                save_last_used_settings_path(filepath)
                return True  # Successfully loaded
        elif filepath is None:
            print("Load cancelled by user.")
        else:
            print(f"Settings file not found: {filepath}")
    except Exception as e:
        print(f"Error loading settings: {e}")
    return False

# Automatically load the last used settings on startup
print("Loading last used settings...")
load_settings()  # This will automatically load the last used file if available

def reset_to_defaults():
    """Reset all settings to their default values"""
    global cursor_rgb_values, trail_rgb_values, current_trail_length
    global enable_trail, trail_fade, enable_main_grid, enable_mini_grid, enable_mini_screen
    global current_smooth, current_thickness, cursor_color, trail_color
    global active_area_values, active_area_rgb_values, active_area_color, active_area_thickness
    global background_rgb_values, BACKGROUND_COLOR, always_on_top, minimap_zoom, region_mode

    # Show confirmation dialog
    root = tk.Tk()
    root.withdraw()
    result = messagebox.askyesno(
        "Reset to Defaults",
        "Are you sure you want to reset all settings to their default values?\n\n"
        "This will reset:\n"
        "• Cursor, trail, area and background colors\n"
        "• Area thickness, trail length, follow speed and trail thickness\n"
        "• All checkboxes except Borderless and Hide UI\n"
        "• Tracking region (back to Full screen)\n\n"
        "This action cannot be undone."
    )
    
    # Restore focus to Pygame window after dialog
    focus_tracker_window()
    
    if result:
        # Reset colors to defaults
        cursor_rgb_values = [0, 255, 255]  # Cyan
        trail_rgb_values = [0, 255, 255]   # Cyan
        active_area_rgb_values = [0, 255, 0]  # Green
        background_rgb_values = [20, 20, 20]  # Dark gray
        
        # Update color tuples
        cursor_color = tuple(cursor_rgb_values)
        trail_color = tuple(trail_rgb_values)
        active_area_color = tuple(active_area_rgb_values)
        BACKGROUND_COLOR = tuple(background_rgb_values)
        
        # Reset numeric values to defaults
        current_trail_length = 15    # Default trail length
        current_smooth = 0.3         # Default smoothness
        current_thickness = 2        # Default thickness
        active_area_thickness = 2    # Default active area thickness
        
        # Reset checkboxes to defaults
        enable_trail = True          # Enable cursor trail
        trail_fade = True            # Enable trail fade
        enable_main_grid = False     # Disable main grid
        enable_mini_grid = True      # Enable mini grid
        enable_mini_screen = True    # Enable mini screen
        minimap_zoom = False
        always_on_top = False
        apply_always_on_top()
        region_mode = 0
        region_values[:] = REGION_DEFAULTS
        set_view()

        # Reset active area values to defaults (these will be calculated based on tablet dimensions)
        # The active area values are set dynamically based on tablet info, so we'll keep current values
        # but reset the styling
        
        print("All settings reset to defaults")
        return True
    else:
        print("Reset cancelled by user")
        return False



def draw_grid(surface, width, height, spacing, color):
    for x in range(0, width, spacing):
        pygame.draw.line(surface, color, (x, 0), (x, height), 1)
    for y in range(0, height, spacing):
        pygame.draw.line(surface, color, (0, y), (width, y), 1)

def draw_checkbox(x, y, text, checked):
    checkbox_size = 20
    checkbox_rect = pygame.Rect(x, y, checkbox_size, checkbox_size)
    pygame.draw.rect(screen, BUTTON_TEXT_COLOR, checkbox_rect, 2)
    if checked:
        pygame.draw.line(screen, BUTTON_TEXT_COLOR, (x+3, y+10), (x+8, y+15), 2)
        pygame.draw.line(screen, BUTTON_TEXT_COLOR, (x+8, y+15), (x+17, y+5), 2)
    
    label = font.render(text, True, BUTTON_TEXT_COLOR)
    screen.blit(label, (x + checkbox_size + 10, y))
    return checkbox_rect.union(label.get_rect(topleft=(x + checkbox_size + 10, y)))  # the label clicks too

def draw_section_header(x, y, text, width=220):
    """Settings section title with a rule under it"""
    screen.blit(font.render(text, True, BUTTON_TEXT_COLOR), (x, y))
    pygame.draw.line(screen, (70, 70, 70), (x, y + 20), (x + width, y + 20))

def draw_button(screen, text, rect, hover, boxed=False):
    if boxed:
        # Settings panel: a bordered box, lighter while hovered
        pygame.draw.rect(screen, INPUT_BOX_ACTIVE_COLOR if hover else INPUT_BOX_COLOR, rect)
        pygame.draw.rect(screen, INPUT_BOX_ACTIVE_BORDER_COLOR if hover else INPUT_BOX_BORDER_COLOR, rect, 2)
        button_text = font.render(text, True, BUTTON_TEXT_COLOR)
        screen.blit(button_text, button_text.get_rect(center=rect.center))
        return
    button_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    button_surface.fill(BUTTON_HOVER_COLOR if hover else BUTTON_COLOR)
    button_surface.set_alpha(150)
    
    button_text = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = button_text.get_rect(center=(rect.width//2, rect.height//2))
    button_surface.blit(button_text, text_rect)
    
    screen.blit(button_surface, rect)

def catmull_rom_spline(p0, p1, p2, p3, num_points=10):
    """Points along the p1->p2 Catmull-Rom segment, excluding p1. Needs p1 != p2."""
    # Tangents scaled to this segment's length, so uneven sample spacing can't overshoot
    d12 = math.dist(p1, p2)
    k1 = d12 / (math.dist(p0, p1) + d12)
    k2 = d12 / (d12 + math.dist(p2, p3))
    m1x, m1y = (p2[0] - p0[0]) * k1, (p2[1] - p0[1]) * k1
    m2x, m2y = (p3[0] - p1[0]) * k2, (p3[1] - p1[1]) * k2
    points = []
    for j in range(1, num_points + 1):
        t = j / num_points
        t2 = t * t
        t3 = t2 * t
        h00, h10, h01, h11 = 2*t3 - 3*t2 + 1, t3 - 2*t2 + t, 3*t2 - 2*t3, t3 - t2
        points.append((h00*p1[0] + h10*m1x + h01*p2[0] + h11*m2x,
                       h00*p1[1] + h10*m1y + h01*p2[1] + h11*m2y))
    return points

def draw_input_box(rect, value, is_active, label_text="", placeholder="", editable=True, tooltip="Click to edit"):
    """Draw a user-friendly input box with hover effects, borders, and cursor"""
    mouse_pos = pygame.mouse.get_pos()
    is_hovered = editable and rect.collidepoint(mouse_pos)
    
    # Determine box color based on state
    if is_active and input_error:
        box_color = INPUT_BOX_ERROR_COLOR
        border_color = INPUT_BOX_ERROR_BORDER_COLOR
    elif is_active:
        box_color = INPUT_BOX_ACTIVE_COLOR
        border_color = INPUT_BOX_ACTIVE_BORDER_COLOR
    elif is_hovered:
        box_color = INPUT_BOX_HOVER_COLOR
        border_color = INPUT_BOX_BORDER_COLOR
    else:
        box_color = INPUT_BOX_COLOR
        border_color = INPUT_BOX_BORDER_COLOR
    
    # Draw input box with border
    pygame.draw.rect(screen, box_color, rect)
    pygame.draw.rect(screen, border_color, rect, 2)
    
    # Add subtle shadow/glow effect for active input
    if is_active:
        # Draw a subtle glow around the active input
        glow_rect = pygame.Rect(rect.x - 2, rect.y - 2, rect.width + 4, rect.height + 4)
        pygame.draw.rect(screen, (100, 150, 255, 50), glow_rect, 1)
    
    # Draw label if provided
    if label_text:
        label = font.render(label_text, True, BUTTON_TEXT_COLOR)
        screen.blit(label, (rect.x - label.get_width() - 10, rect.y + 5))
    
    # Draw text content
    if is_active:
        if input_text != "":
            display_text = input_text
            text_color = INPUT_TEXT_COLOR
        else:
            display_text = ""  # Show empty when actively editing and no text
            text_color = INPUT_PLACEHOLDER_COLOR
    elif str(value) != "":
        display_text = str(value)
        text_color = INPUT_TEXT_COLOR
    else:
        display_text = placeholder
        text_color = INPUT_PLACEHOLDER_COLOR
    
    # Render text
    text_surface = font.render(display_text, True, text_color)
    
    # Calculate text position (center vertically, left align with padding)
    text_x = rect.x + 8
    text_y = rect.y + (rect.height - text_surface.get_height()) // 2
    
    # Clip text if it's too long; while editing, show its end where the cursor is
    if text_surface.get_width() > rect.width - 16:
        # Create a clipped surface
        clipped_surface = pygame.Surface((rect.width - 16, text_surface.get_height()))
        clipped_surface.fill(box_color)
        clipped_surface.blit(text_surface, (rect.width - 16 - text_surface.get_width() if is_active else 0, 0))
        screen.blit(clipped_surface, (text_x, text_y))
    else:
        screen.blit(text_surface, (text_x, text_y))

    # Draw cursor if active
    if is_active:
        if input_text != "":
            cursor_x = text_x + min(font.render(input_text, True, text_color).get_width(), rect.width - 16)
        else:
            cursor_x = text_x  # Cursor at start when input is empty
        cursor_y = text_y
        cursor_height = text_surface.get_height()
        
        # Blinking cursor effect (simple implementation)
        if pygame.time.get_ticks() % 1000 < 500:
            pygame.draw.line(screen, INPUT_TEXT_COLOR, 
                           (cursor_x, cursor_y), 
                           (cursor_x, cursor_y + cursor_height), 2)
    
    # Draw hover tooltip, kept inside the window
    if is_hovered and not is_active:
        tooltip_surface = font.render(tooltip, True, (200, 200, 200))
        tooltip_rect = tooltip_surface.get_rect()
        tooltip_rect.topleft = (min(rect.x, WIN_WIDTH - tooltip_rect.width - 10), rect.y - 25)

        # Draw tooltip background
        tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                               tooltip_rect.width + 10, tooltip_rect.height + 4)
        pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
        pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
        screen.blit(tooltip_surface, tooltip_rect)

def draw_color_section(x, y_offset, title, rgb_values, input_name):
    """Label, a swatch that opens the picker, and a hex box; returns (swatch, hex box) rects"""
    hex_input_active = active_input == input_name
    hex_input_text = input_text if hex_input_active else ""
    # Draw section title
    section_title = font.render(title, True, BUTTON_TEXT_COLOR)
    screen.blit(section_title, (x, y_offset))

    # Draw color preview (clickable)
    preview_rect = pygame.Rect(x, y_offset + 25, 80, 40)
    pygame.draw.rect(screen, rgb_values, preview_rect)
    pygame.draw.rect(screen, BUTTON_TEXT_COLOR, preview_rect, 2)  # Border
    
    # Add hover tooltip for color picker
    mouse_pos = pygame.mouse.get_pos()
    if preview_rect.collidepoint(mouse_pos):
        tooltip_text = "Click to use RGB selector"
        tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
        tooltip_rect = tooltip_surface.get_rect()
        tooltip_rect.topleft = (preview_rect.x, preview_rect.y - 25)
        
        # Draw tooltip background
        tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                               tooltip_rect.width + 10, tooltip_rect.height + 4)
        pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
        pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
        screen.blit(tooltip_surface, tooltip_rect)
    
    # Draw hex input box to the right of the preview (longer than before)
    hex_value = rgb_to_hex(*rgb_values)
    # Check if this hex input is currently active
    is_active = False
    if hex_input_active:
        is_active = True
        display_text = hex_input_text
        text_color = INPUT_TEXT_COLOR
    else:
        display_text = hex_value
        text_color = INPUT_TEXT_COLOR
    
    # Make hex input box longer (120px instead of 70px)
    input_box_width = 120
    input_box_height = 30
    input_box_x = preview_rect.right + 10  # 10px margin to the right
    input_box_y = preview_rect.y + (preview_rect.height - input_box_height) // 2
    input_rect = pygame.Rect(input_box_x, input_box_y, input_box_width, input_box_height)
    
    # Use the same styling as Active Area inputs
    mouse_pos = pygame.mouse.get_pos()
    is_hovered = input_rect.collidepoint(mouse_pos)
    
    # Determine box color based on state (same as draw_input_box)
    if is_active and input_error:
        box_color = INPUT_BOX_ERROR_COLOR
        border_color = INPUT_BOX_ERROR_BORDER_COLOR
    elif is_active:
        box_color = INPUT_BOX_ACTIVE_COLOR
        border_color = INPUT_BOX_ACTIVE_BORDER_COLOR
    elif is_hovered:
        box_color = INPUT_BOX_HOVER_COLOR
        border_color = INPUT_BOX_BORDER_COLOR
    else:
        box_color = INPUT_BOX_COLOR
        border_color = INPUT_BOX_BORDER_COLOR
    
    # Draw input box with border
    pygame.draw.rect(screen, box_color, input_rect)
    pygame.draw.rect(screen, border_color, input_rect, 2)
    
    # Add subtle shadow/glow effect for active input
    if is_active:
        # Draw a subtle glow around the active input
        glow_rect = pygame.Rect(input_rect.x - 2, input_rect.y - 2, input_rect.width + 4, input_rect.height + 4)
        pygame.draw.rect(screen, (100, 150, 255, 50), glow_rect, 1)
    
    # Draw text left-aligned with padding (same as draw_input_box)
    text_x = input_rect.x + 8
    text_y = input_rect.y + (input_rect.height - font.get_height()) // 2
    text_surface = font.render(display_text, True, text_color)
    screen.blit(text_surface, (text_x, text_y))
    
    # Draw cursor if active (same as draw_input_box)
    if is_active:
        if input_text != "":
            cursor_x = text_x + font.render(input_text, True, text_color).get_width()
        else:
            cursor_x = text_x  # Cursor at start when input is empty
        cursor_y = text_y
        cursor_height = text_surface.get_height()
        
        # Blinking cursor effect (same as draw_input_box)
        if pygame.time.get_ticks() % 1000 < 500:
            pygame.draw.line(screen, INPUT_TEXT_COLOR, 
                           (cursor_x, cursor_y), 
                           (cursor_x, cursor_y + cursor_height), 2)
    
    # Draw hover tooltip (same as draw_input_box)
    if is_hovered and not is_active:
        tooltip_text = "Click to edit"
        tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
        tooltip_rect = tooltip_surface.get_rect()
        tooltip_rect.topleft = (input_rect.x, input_rect.y - 25)
        
        # Draw tooltip background
        tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                               tooltip_rect.width + 10, tooltip_rect.height + 4)
        pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
        pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
        screen.blit(tooltip_surface, tooltip_rect)
    
    # Return preview_rect and input_rect for click detection
    return preview_rect, input_rect

def draw_slider(x, y, width, value, min_val, max_val, label, shown=None, grabbed=False):
    # Draw slider label; shown = the value as text, when it isn't the raw number
    label_text = font.render(f"{label}: {value if shown is None else shown}", True, BUTTON_TEXT_COLOR)
    screen.blit(label_text, (x, y - 20))
    
    # Draw slider track
    slider_rect = pygame.Rect(x, y, width, SLIDER_HEIGHT)
    pygame.draw.rect(screen, SLIDER_COLOR, slider_rect)
    
    # Calculate and draw slider handle
    handle_pos = x + (value - min_val) * width / (max_val - min_val)
    handle_rect = pygame.Rect(handle_pos - 5, y - 5, 10, SLIDER_HEIGHT + 10)
    
    # Highlight if mouse is over handle
    mouse_pos = pygame.mouse.get_pos()
    if handle_rect.collidepoint(mouse_pos) or grabbed:
        pygame.draw.rect(screen, SLIDER_HOVER_COLOR, handle_rect)
    else:
        pygame.draw.rect(screen, BUTTON_TEXT_COLOR, handle_rect)
    
    return slider_rect, handle_rect

def launch_stats_window():
    """Launch the separate statistics window as a new process"""
    try:
        # Use Python executable path to avoid issues with different environments
        python_executable = sys.executable
        stats_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key_stats.py")
        
        # Check if key_stats.py exists
        if not os.path.exists(stats_script_path):
            show_message("Error: key_stats.py not found", 2000)
            return
            
        # Launch as a separate process
        subprocess.Popen([python_executable, stats_script_path])
    except Exception as e:
        print(f"Error launching stats window: {e}")
        show_message(f"Error launching stats", 1000)

# --- Tooltip Overlay and UI/Window State ---
tooltip_active = False  # Whether the Alt-tooltip is active
hide_ui = False         # Whether to hide all UI (option 2/3)
hide_minimap = False    # Whether to hide minimap (option 3)
borderless = False      # Whether window is borderless (option 1)

# Helper to set borderless mode
def set_borderless(enable):
    global borderless
    borderless = enable
    flags = pygame.NOFRAME if enable else 0
    pygame.display.set_mode((WIN_WIDTH, WIN_HEIGHT), flags)
    pygame.display.set_caption("Simple Cursor Tracking")
    apply_always_on_top()

def toggle_overlay_mode(hide_map):
    """Alt menu 2/3 and the OBS checkboxes: hide the UI (and the mini-map), or undo that same mode"""
    global hide_ui, hide_minimap
    if hide_ui and hide_minimap == hide_map:
        hide_ui = hide_minimap = False
    else:
        hide_ui, hide_minimap = True, hide_map

# Tooltip overlay drawing
def draw_tooltip_overlay():
    overlay = pygame.Surface((WIN_WIDTH, WIN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))
    title = font.render("OBS Overlay Options (Press 1/2/3)", True, (255,255,255))
    screen.blit(title, (WIN_WIDTH//2 - title.get_width()//2, 120))
    opt1 = font.render("1. Borderless Window (for OBS capture)", True, (220,220,220))
    opt2 = font.render("2. Hide UI (settings, overlays)", True, (220,220,220))
    opt3 = font.render("3. Hide UI + Minimap", True, (220,220,220))
    screen.blit(opt1, (WIN_WIDTH//2 - opt1.get_width()//2, 180))
    screen.blit(opt2, (WIN_WIDTH//2 - opt2.get_width()//2, 220))
    screen.blit(opt3, (WIN_WIDTH//2 - opt3.get_width()//2, 260))
    hint = font.render("Press Alt to close this menu", True, (180,180,180))
    screen.blit(hint, (WIN_WIDTH//2 - hint.get_width()//2, 320))

def draw_thick_line_with_caps(surface, color, start, end, thickness):
    """Draw a line of the same width at every angle, with a round cap at the end point"""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    half = thickness / 2
    # pygame truncates float coordinates; +0.5 makes that rounding so the stroke stays centred
    sx, sy, ex, ey = start[0] + 0.5, start[1] + 0.5, end[0] + 0.5, end[1] + 0.5
    if length:
        nx, ny = -dy / length * half, dx / length * half
        pygame.draw.polygon(surface, color, [(sx + nx, sy + ny), (ex + nx, ey + ny), (ex - nx, ey - ny), (sx - nx, sy - ny)])
    pygame.draw.circle(surface, color, (ex, ey), (thickness + 1) / 2)

def draw_dashed_line(surface, color, start, end, dash=3):
    """1-px line of dash-px dashes and gaps"""
    length = math.dist(start, end)
    for i in range(0, math.ceil(length / dash), 2):
        a, b = i * dash / length, min((i + 1) * dash / length, 1)
        pygame.draw.line(surface, color, (round(start[0] + (end[0] - start[0]) * a), round(start[1] + (end[1] - start[1]) * a)),
                         (round(start[0] + (end[0] - start[0]) * b), round(start[1] + (end[1] - start[1]) * b)))

def render_trail(screen, trail, trail_color, current_thickness, enable_trail=True, trail_fade=True, fades=None):
    """Draw the trail as one Catmull-Rom smoothed stroke, fading from the background colour to trail_color.
    fades: each point's level, 0 = background to 1 = trail_color; default evenly by index"""
    if not enable_trail or len(trail) < 2:
        return
    last = len(trail) - 1
    if fades is None:
        fades = [i / last for i in range(last + 1)]
    if not trail_fade:
        pygame.draw.circle(screen, trail_color, (trail[0][0] + 0.5, trail[0][1] + 0.5), (current_thickness + 1) / 2)
    for i in range(last):
        p1, p2 = trail[i], trail[i + 1]
        segment_length = math.dist(p1, p2)
        if segment_length == 0:
            continue
        p0 = trail[i - 1] if i > 0 else p1
        p3 = trail[i + 2] if i + 2 <= last else p2
        steps = max(1, min(12, int(segment_length / 6)))  # about one sample per 6 px
        start = p1
        for j, end in enumerate(catmull_rom_spline(p0, p1, p2, p3, steps) if steps > 1 else [p2], 1):  # 1 step ends at p2
            if trail_fade:
                fade = fades[i] + (fades[i + 1] - fades[i]) * (j - 0.5) / steps
                current_color = [round(b + (c - b) * fade) for c, b in zip(trail_color, BACKGROUND_COLOR)]
            else:
                current_color = trail_color
            draw_thick_line_with_caps(screen, current_color, start, end, current_thickness)
            start = end

def smooth_trail_to(t):
    """Move the smoothed point toward trail_target until time t and record it in the trail"""
    global prev_x, prev_y, smooth_time
    t = max(t, smooth_time)  # a sample queued during the last drain can be older than the frame
    dt, smooth_time = t - smooth_time, t
    # Smoothness was a per-60 Hz-frame step; this time constant gives the same lag while moving
    k = 1.0 if current_smooth >= 1 else 1 - math.exp(-dt * 60 * current_smooth / (1 - current_smooth))
    prev_x += (trail_target[0] - prev_x) * k
    prev_y += (trail_target[1] - prev_y) * k
    if abs(trail_target[0] - prev_x) < 0.05 and abs(trail_target[1] - prev_y) < 0.05:
        prev_x, prev_y = trail_target  # settle exactly so the idle skip sees a still trail
    point = (prev_x, prev_y)
    if trail and point == trail[-1]:
        # Still: a duplicate point carries the time it left, so the trail ages from there
        if len(trail) > 1 and trail[-2] != point:
            trail.append(point)
            trail_times.append(t)
        else:
            trail_times[-1] = t
        return
    if len(trail) > 1 and trail[-2] != trail[-1]:
        # The head moves on until TRAIL_STEP from the last kept point; turning back keeps it as a tip
        head = math.dist(trail[-2], trail[-1])
        if head < TRAIL_STEP and head <= math.dist(trail[-2], point):
            trail[-1], trail_times[-1] = point, t
            return
    trail.append(point)
    trail_times.append(t)

def prune_trail(cutoff):
    """Drop trail points older than cutoff, moving the tail to where the stroke was at cutoff"""
    while len(trail) > 1 and trail_times[1] <= cutoff:
        del trail[0], trail_times[0]
    if len(trail) > 1 and trail_times[0] < cutoff:
        f = (cutoff - trail_times[0]) / (trail_times[1] - trail_times[0])
        (x0, y0), (x1, y1) = trail[0], trail[1]
        trail[0], trail_times[0] = (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), cutoff
    if len(trail) == 2 and trail[0] == trail[1]:
        del trail[0], trail_times[0]

# Add this helper function near the top, after global variable definitions:
def deactivate_all_inputs():
    global active_input
    global cursor_hex_input_active, trail_hex_input_active, rectangle_hex_input_active, background_hex_input_active
    active_input = None
    cursor_hex_input_active = False
    trail_hex_input_active = False
    rectangle_hex_input_active = False
    background_hex_input_active = False

def tab_order():
    """Editable fields in reading order: hex boxes, the area fields while unlocked, then the region fields in use"""
    order = ["cursor_hex", "trail_hex", "rectangle_hex", "background_hex"]
    if not active_area_locked:
        order += ["active_2", "active_3", "active_0", "active_1", "active_4"]  # Width, Height, X, Y, Rotation
    return order + [f"region_{i}" for i in region_fields()]

def drag_slider(x):
    """Set the grabbed slider's value from the pointer's x on its track"""
    global current_trail_length, current_smooth, current_thickness, active_area_thickness
    track = {"trail": trail_length_slider, "smooth": smooth_factor_slider,
             "thickness": trail_thickness_slider, "active_area_thickness": area_thickness_slider}[slider_grabbed]
    f = min(max((x - track.x) / track.width, 0), 1)
    if slider_grabbed == "trail":
        current_trail_length = round(min_trail_length + (max_trail_length_limit - min_trail_length) * f)
    elif slider_grabbed == "smooth":
        current_smooth = round(min_smooth + (max_smooth - min_smooth) * f, 2)
    elif slider_grabbed == "thickness":
        current_thickness = round(min_thickness + (max_thickness - min_thickness) * f)
    else:
        active_area_thickness = round(1 + 4 * f)

def get_active_area_from_settings(settings, target_model=None):
    """
    Returns (tablet_name, area, display, abs_tablet) for the matching model.
    area: [x, y, x+width, y+height] if AbsoluteModeSettings.Tablet is found.
    abs_tablet: the dict with Width, Height, X, Y.
    """
    for profile in settings.get("Profiles", []):
        name = profile.get("Tablet") or profile.get("Name") or profile.get("Model") or "Unknown"
        if target_model and name != target_model:
            continue
        abs_mode = profile.get("AbsoluteModeSettings")
        if abs_mode and "Tablet" in abs_mode:
            tab = abs_mode["Tablet"]
            if all(k in tab for k in ("Width", "Height", "X", "Y")):
                # Compose area as [x, y, x+width, y+height]
                area = [tab["X"], tab["Y"], tab["X"] + tab["Width"], tab["Y"] + tab["Height"]]
                display = abs_mode.get("Display")
                return name, area, display, tab
    # Fallback to old logic if not found
    return try_get_tablet_info(settings)

# Idle skip state: what the last drawn frame showed, and whether input arrived since
last_frame_state = None
had_events = True

# Start the cursor sampler; from here on only it calls get_cursor_pos (shared POINT buffer)
mouse_x, mouse_y = get_cursor_pos()
sampler = threading.Thread(target=sample_cursor, daemon=True)
sampler.start()

# Settings panel hit rects; each drawn frame replaces them, so clicks test what is on screen
save_rect = load_rect = reset_rect = close_rect = pygame.Rect(0, 0, 0, 0)
trail_checkbox = fade_checkbox = main_grid_checkbox = mini_grid_checkbox = mini_screen_checkbox = pygame.Rect(0, 0, 0, 0)
zoom_checkbox = borderless_checkbox = topmost_checkbox = hide_ui_checkbox = hide_all_checkbox = pygame.Rect(0, 0, 0, 0)
region_mode_rect = pygame.Rect(0, 0, 0, 0)

# Main game loop
while running:
    # Every cursor change since the last frame, oldest first; mouse_x/mouse_y end on the newest
    while cursor_samples:
        sample_time, mouse_x, mouse_y = cursor_samples.popleft()
        smooth_trail_to(sample_time)
        trail_target = screen_to_view(mouse_x, mouse_y)

    # Borderless drag: keep the grabbed point under the sampled cursor
    if window_drag:
        if pygame.mouse.get_pressed()[0]:
            user32.SetWindowPos(window_handle(), None, mouse_x - window_drag[0], mouse_y - window_drag[1], 0, 0,
                                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        else:
            window_drag = None  # released without a MOUSEBUTTONUP

    # Handle continuous backspace hold
    if backspace_held and active_input is not None:
        current_time = pygame.time.get_ticks()
        time_since_start = current_time - backspace_start_time
        
        if time_since_start > backspace_repeat_delay:
            # Calculate how many times to repeat based on time
            repeat_count = (time_since_start - backspace_repeat_delay) // backspace_repeat_interval
            
            # Perform backspace action
            if active_input.endswith("_hex") and len(input_text) > 1:
                if input_text.startswith('#'):
                    input_text = input_text[:-1]
                else:
                    input_text = '#' + input_text[1:-1]
            else:
                input_text = input_text[:-1]
            
            # Update color in real-time for RGB inputs
            if active_input.startswith("cursor") or active_input.startswith("trail"):
                update_color_in_realtime()
            
            # Update start time to prevent multiple deletions in one frame
            backspace_start_time = current_time - (repeat_count * backspace_repeat_interval)

    # Where the pen is on the tablet, in mm
    tablet_mouse_x, tablet_mouse_y = screen_to_tablet(mouse_x, mouse_y)

    # Trail = the last (length - 1) frames of 60 Hz, faded by age
    now = time.perf_counter()
    smooth_trail_to(now)
    trail_span = max(current_trail_length - 1, 1) / 60
    prune_trail(now - trail_span)

    # Nothing moved, nothing open, no input: the last frame is still correct, skip drawing it
    # (a trail of 2+ points is still fading out)
    frame_state = (mouse_x, mouse_y, tuple(trail))
    if (len(trail) < 2 and frame_state == last_frame_state and not had_events and not pygame.event.peek()
            and not (settings_open or color_picker_open or tooltip_active)):
        clock.tick(60)
        continue
    last_frame_state = frame_state

    screen.fill(BACKGROUND_COLOR)
    small_screen.fill((10, 10, 10))

    mouse_pos = pygame.mouse.get_pos()
    # Rebuilt from the OTD-read (or edited) values each frame, so a preset's area never replaces them
    active_area_values = [active_area_x, active_area_y, active_area_width, active_area_height, active_area_rotation]
    #print(f"BEFORE SETTINGS SHOWS: {active_area_values}")
    #print(f"Active Areaadddddddddddddddd: {active_area_values}")
    if settings_open:
        #print("DEBUG: active_area_values before draw:", active_area_values)
        #break
        # Hide mini screen when settings are open (regardless of toggle)
        mini_visible = False
        
        # Draw full screen modal
        screen.fill(MODAL_BG_COLOR)
        
        # Draw title
        title = font.render("Settings", True, BUTTON_TEXT_COLOR)
        title_rect = title.get_rect(centerx=WIN_WIDTH//2, y=20)
        screen.blit(title, title_rect)
        
        # Grid: three 220-px columns. Row 1: Colors | Trail | Minimap + OBS. Row 2: Active Area (2 columns) | Tracking region.
        col_x = (40, 290, 540)
        row_y = (64, 432)

        # Colors (column 1)
        x, y = col_x[0], row_y[0]
        draw_section_header(x, y, "Colors")
        cursor_color_preview_rect, cursor_hex_input_rect = draw_color_section(x, y + 28, "Cursor color", cursor_rgb_values, "cursor_hex")
        trail_color_preview_rect, trail_hex_input_rect = draw_color_section(x, y + 104, "Trail color", trail_rgb_values, "trail_hex")
        active_area_color_preview_rect, rectangle_hex_input_rect = draw_color_section(
            x, y + 180, "Area color", active_area_rgb_values, "rectangle_hex")
        background_color_preview_rect, background_hex_input_rect = draw_color_section(
            x, y + 256, "Background color", background_rgb_values, "background_hex")

        # Trail (column 2); length shows its real duration, (N-1)/60 s
        x, y = col_x[1], row_y[0]
        draw_section_header(x, y, "Trail")
        trail_checkbox = draw_checkbox(x, y + 28, "Cursor trail", enable_trail)
        fade_checkbox = draw_checkbox(x, y + 56, "Trail fade", trail_fade)
        main_grid_checkbox = draw_checkbox(x, y + 84, "Main grid", enable_main_grid)
        trail_length_slider, _ = draw_slider(
            x, y + 142, SLIDER_WIDTH, current_trail_length, min_trail_length, max_trail_length_limit,
            "Trail length", f"{round((current_trail_length - 1) * 1000 / 60)} ms", slider_grabbed == "trail")
        smooth_factor_slider, _ = draw_slider(
            x, y + 190, SLIDER_WIDTH, current_smooth, min_smooth, max_smooth,
            "Follow speed", f"{current_smooth:.2f}", slider_grabbed == "smooth")
        trail_thickness_slider, _ = draw_slider(
            x, y + 238, SLIDER_WIDTH, current_thickness, min_thickness, max_thickness,
            "Trail thickness", grabbed=slider_grabbed == "thickness")

        # Minimap (column 3)
        x, y = col_x[2], row_y[0]
        draw_section_header(x, y, "Minimap")
        mini_screen_checkbox = draw_checkbox(x, y + 28, "Show minimap", enable_mini_screen)
        mini_grid_checkbox = draw_checkbox(x, y + 56, "Minimap grid", enable_mini_grid)
        zoom_checkbox = draw_checkbox(x, y + 84, "Zoom to area", minimap_zoom)
        area_thickness_slider, _ = draw_slider(
            x, y + 142, SLIDER_WIDTH, active_area_thickness, 1, 5,
            "Area thickness", grabbed=slider_grabbed == "active_area_thickness")

        # OBS (column 3, under Minimap): the Alt menu's states, plus always on top
        y = row_y[0] + 180
        draw_section_header(x, y, "OBS")
        borderless_checkbox = draw_checkbox(x, y + 28, "Borderless", borderless)
        topmost_checkbox = draw_checkbox(x, y + 56, "Always on top", always_on_top)
        hide_ui_checkbox = draw_checkbox(x, y + 84, "Hide UI", hide_ui and not hide_minimap)
        hide_all_checkbox = draw_checkbox(x, y + 112, "Hide UI + minimap", hide_ui and hide_minimap)
        for i, hint in enumerate(("Alt + 1/2/3 also toggle these", "Borderless: drag to move")):
            screen.blit(font.render(hint, True, (150, 150, 150)), (x, y + 142 + i * 18))

        # Active Area (row 2, columns 1-2), OTD's numbers: X/Y are the area's centre
        x, y = col_x[0], row_y[1]
        area_width = col_x[1] + 220 - x
        draw_section_header(x, y, "Active Area (mm)", area_width)
        clicks_left = 3 - active_area_unlock_clicks
        if not active_area_locked:
            lock_hint = "Unlocked"
        elif clicks_left == 3:
            lock_hint = "Locked: click 3 times to unlock"
        else:
            lock_hint = f"Click {clicks_left} more time{'s' if clicks_left > 1 else ''} to unlock"
        screen.blit(font.render(lock_hint, True, (150, 150, 150)), (x + font.size("Active Area (mm)")[0] + 15, y))
        active_area_section = pygame.Rect(x - 4, y - 6, area_width + 8, 106)

        # Width, Height / X, Y, Rotation; shown to 2 decimals, kept at full precision
        column_x = (x + 60, x + 220, x + 390)
        for row, fields in enumerate((((2, "Width:"), (3, "Height:")), ((0, "X:"), (1, "Y:"), (4, "Rotation:")))):
            for column, (i, label) in enumerate(fields):
                active_area_inputs[i].topleft = (column_x[column], y + 28 + row * 38)
                draw_input_box(active_area_inputs[i], f"{active_area_values[i]:.2f}", active_input == f"active_{i}",
                               label, editable=not active_area_locked)

        # Locked: dim the fields without hiding the values
        if active_area_locked:
            dim_surface = pygame.Surface((active_area_section.width, 76), pygame.SRCALPHA)
            dim_surface.fill((*MODAL_BG_COLOR, 110))
            screen.blit(dim_surface, (active_area_section.x, y + 24))

            mouse_pos = pygame.mouse.get_pos()
            if active_area_section.collidepoint(mouse_pos):
                tooltip_text = "Read from OTD. Edits change only this mini-map, not OTD."
                tooltip_surface = font.render(tooltip_text, True, (255, 200, 200))
                tooltip_rect = tooltip_surface.get_rect()
                tooltip_rect.topleft = (active_area_section.x, active_area_section.y - 40)

                # Draw tooltip background
                tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2,
                                       tooltip_rect.width + 10, tooltip_rect.height + 4)
                pygame.draw.rect(screen, (60, 40, 40), tooltip_bg)
                pygame.draw.rect(screen, (200, 100, 100), tooltip_bg, 1)
                screen.blit(tooltip_surface, tooltip_rect)

        # Tracking region (row 2, column 3): mode (click a side to step), sensitivity, then position and scale (H, V)
        x, y = col_x[2], row_y[1]
        draw_section_header(x, y, "Tracking region")
        region_mode_rect = pygame.Rect(x, y + 25, 150, 22)
        draw_button(screen, f"< {REGION_MODES[region_mode]} >", region_mode_rect, region_mode_rect.collidepoint(mouse_pos), boxed=True)
        region_inputs[4].update(x + 158, y + 25, 62, 22)
        for i, label in enumerate(("Position:", "Scale:")):
            region_inputs[2 * i].update(x + 80, y + 51 + i * 26, 66, 22)
            region_inputs[2 * i + 1].update(x + 154, y + 51 + i * 26, 66, 22)
            label_surface = font.render(label, True, BUTTON_TEXT_COLOR)
            screen.blit(label_surface, label_surface.get_rect(right=x + 72, centery=region_inputs[2 * i].centery))
        for i in (4, 0, 1, 2, 3):  # top row first, so a hover tooltip stays on top
            enabled, unit = i in region_fields(), "x" if i == 4 else "%"
            draw_input_box(region_inputs[i], f"{region_values[i]:g}{unit}", active_input == f"region_{i}", editable=enabled,
                           tooltip=f"lazer {REGION_LABELS[i]}, {REGION_LIMITS[i][0]:g}-{REGION_LIMITS[i][1]:g}{unit}")
            if not enabled:  # unused by this mode: dimmed, value still readable
                dim_surface = pygame.Surface(region_inputs[i].size, pygame.SRCALPHA)
                dim_surface.fill((*MODAL_BG_COLOR, 150))
                screen.blit(dim_surface, region_inputs[i])

        # Bottom bar: preset file actions on the left, Close on the right
        pygame.draw.line(screen, (70, 70, 70), (col_x[0], 538), (WIN_WIDTH - col_x[0], 538))
        save_rect = pygame.Rect(col_x[0], 550, 90, 32)
        load_rect = pygame.Rect(col_x[0] + 100, 550, 90, 32)
        reset_rect = pygame.Rect(col_x[0] + 200, 550, 90, 32)
        close_rect = pygame.Rect(WIN_WIDTH - col_x[0] - 90, 550, 90, 32)
        for rect, text in ((save_rect, "Save"), (load_rect, "Load"), (reset_rect, "Reset"), (close_rect, "Close")):
            draw_button(screen, text, rect, rect.collidepoint(mouse_pos), boxed=True)

        # Editing help, between the buttons
        if active_input is not None:
            if input_error:
                help_text, help_color = error_message, (255, 150, 150)
            else:
                help_text, help_color = "Enter: apply   Esc: cancel   Tab: next", (150, 150, 150)
            help_surface = font.render(help_text, True, help_color)
            screen.blit(help_surface, help_surface.get_rect(center=((reset_rect.right + close_rect.left) // 2, close_rect.centery)))
    
    # Draw color picker popup if open
    if color_picker_open:
        popup_elements = draw_color_picker_popup()
    
    elif not settings_open:
        # Only show main content when settings are closed
        # Show mini screen when settings are closed (based on toggle)
        mini_visible = enable_mini_screen and not hide_minimap

        # Always draw trail if enabled and has enough points
        render_trail(screen, trail, trail_color, current_thickness, enable_trail, trail_fade,
                     [1 - (now - t) / trail_span for t in trail_times])

        # Always draw cursor
        if trail:
            pygame.draw.circle(screen, cursor_color, (trail[-1][0] + 0.5, trail[-1][1] + 0.5), 5)

        if not hide_ui:
            # Draw main grid if enabled, over the tracking region only (not the letterbox bars)
            if enable_main_grid:
                grid_rect = view_rect()
                draw_grid(screen.subsurface(grid_rect), grid_rect.width, grid_rect.height, GRID_SPACING, GRID_COLOR)

            # Draw settings button (only when settings are closed)
            button_hover = button_rect.collidepoint(mouse_pos)
            draw_button(screen, "Settings", button_rect, button_hover)

    # This goes in your main update loop, not inside event loop!
    if active_area_locked and active_area_unlock_clicks > 0:
        current_time = pygame.time.get_ticks()
        if current_time - active_area_unlock_timer > 3000:  # 3 seconds timeout
            active_area_unlock_clicks = 0  # ❗ Reset if too slow

    
    # Always update and draw mini display if enabled
    if mini_visible and not hide_minimap:
        # Clear mini display
        small_screen.fill((10, 10, 10))

        # Active area = the display's corners mapped back onto the tablet, so it follows OTD's rotation
        centre_x, centre_y, display_w, display_h = display_area
        area_corners = [screen_to_tablet(centre_x + sx * display_w / 2, centre_y + sy * display_h / 2)
                        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        if minimap_zoom:
            # Frame the area's bounding box plus a quarter of its longer side
            xs, ys = [c[0] for c in area_corners], [c[1] for c in area_corners]
            pad = max(max(xs) - min(xs), max(ys) - min(ys)) / 4
            minimap_view = (min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
        else:
            minimap_view = (0, 0, tablet_width, tablet_height)

        # Full tablet outline (white), upright at its real aspect; zoomed in, only edges inside the view show
        left, top = tablet_to_minimap(0, 0)
        right, bottom = tablet_to_minimap(tablet_width, tablet_height)
        tablet_outline = pygame.Rect(round(left), round(top), round(right - left), round(bottom - top))
        tablet_rect = tablet_outline.clip(small_screen.get_rect())

        # Draw mini grid if enabled
        if enable_mini_grid:
            draw_grid(small_screen.subsurface(tablet_rect), tablet_rect.width, tablet_rect.height, 10, GRID_COLOR)
        pygame.draw.rect(small_screen, (255, 255, 255), tablet_outline, 2)

        corners = [tablet_to_minimap(*corner) for corner in area_corners]
        for i in range(4):
            draw_thick_line_with_caps(small_screen, active_area_color, corners[i - 1], corners[i], active_area_thickness)

        # Tracking region (osu! modes): its screen corners mapped onto the tablet, dashed
        if region_mode:
            rx, ry, rw, rh = tracking_region()
            region_corners = [tablet_to_minimap(*screen_to_tablet(rx + fx * rw, ry + fy * rh))
                              for fx, fy in ((0, 0), (1, 0), (1, 1), (0, 1))]
            for i in range(4):
                draw_dashed_line(small_screen, REGION_COLOR, region_corners[i - 1], region_corners[i])

        # Map cursor position to mini display
        mini_cursor_x, mini_cursor_y = tablet_to_minimap(tablet_mouse_x, tablet_mouse_y)

        # Draw mini cursor
        pygame.draw.circle(small_screen, cursor_color, (int(mini_cursor_x), int(mini_cursor_y)), 3)

        # Draw to main screen
        screen.blit(small_screen, minimap_rect)

    if tooltip_active:
        draw_tooltip_overlay()
    pygame.display.update()
    clock.tick(60)

    events = pygame.event.get()
    had_events = bool(events)
    for event in events:
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                # Handle color picker popup interactions first (highest priority)
                if color_picker_open:
                    popup_elements = draw_color_picker_popup()
                    
                    # Check for button clicks
                    if popup_elements['apply_button'].collidepoint(event.pos):
                        # Apply the color
                        if color_picker_type == "cursor":
                            cursor_rgb_values = color_picker_temp_values.copy()
                            cursor_color = tuple(cursor_rgb_values)
                        elif color_picker_type == "trail":
                            trail_rgb_values = color_picker_temp_values.copy()
                            trail_color = tuple(trail_rgb_values)
                        elif color_picker_type == "active_area":
                            active_area_rgb_values = color_picker_temp_values.copy()
                            active_area_color = tuple(active_area_rgb_values)
                        elif color_picker_type == "background":
                            background_rgb_values = color_picker_temp_values.copy()
                            BACKGROUND_COLOR = tuple(background_rgb_values)
                        color_picker_open = False
                        color_picker_type = None
                        continue
                    
                    elif popup_elements['cancel_button'].collidepoint(event.pos):
                        # Cancel - close picker without applying
                        color_picker_open = False
                        color_picker_type = None
                        continue
                    
                    # Check for slider clicks to start dragging
                    wheel_center = popup_elements['wheel_center']
                    wheel_radius = popup_elements['wheel_radius']
                    distance = ((event.pos[0] - wheel_center[0])**2 + (event.pos[1] - wheel_center[1])**2)**0.5
                    
                    if distance <= wheel_radius:
                        # Start dragging the color wheel
                        color_picker_dragging = True
                        color_picker_drag_type = "wheel"
                        continue
                    
                    # Check value slider
                    vs_x, vs_y, vs_w, vs_h = popup_elements['value_slider']
                    if vs_x <= event.pos[0] <= vs_x + vs_w and vs_y <= event.pos[1] <= vs_y + vs_h:
                        color_picker_dragging = True
                        color_picker_drag_type = "value_slider"
                        continue
                    
                    # Check RGB sliders
                    if popup_elements['r_slider'].collidepoint(event.pos):
                        color_picker_dragging = True
                        color_picker_drag_type = "r_slider"
                        continue
                    elif popup_elements['g_slider'].collidepoint(event.pos):
                        color_picker_dragging = True
                        color_picker_drag_type = "g_slider"
                        continue
                    elif popup_elements['b_slider'].collidepoint(event.pos):
                        color_picker_dragging = True
                        color_picker_drag_type = "b_slider"
                        continue
                    
                    continue
                # Handle normal UI clicks (only when color picker is closed)
                if not settings_open:
                    if button_rect.collidepoint(event.pos):
                        settings_open = True
                    elif borderless and not (mini_visible and minimap_rect.collidepoint(event.pos)):
                        # No title bar: dragging the empty view moves the window
                        drag_rect, drag_origin = wintypes.RECT(), wintypes.POINT(0, 0)
                        user32.GetWindowRect(window_handle(), ctypes.byref(drag_rect))
                        user32.ClientToScreen(window_handle(), ctypes.byref(drag_origin))
                        window_drag = (event.pos[0] + drag_origin.x - drag_rect.left, event.pos[1] + drag_origin.y - drag_rect.top)
                else:
                    if close_rect.collidepoint(event.pos):
                        settings_open = False
                    elif save_rect.collidepoint(event.pos):
                        if save_settings():
                            show_message("Settings saved!")
                    elif load_rect.collidepoint(event.pos):
                        # Always show file dialog for manual selection
                        if load_settings(manual_load=True):  # This will show the file dialog
                            show_message("Settings loaded!")
                        else:
                            show_message("No settings loaded.")
                    elif reset_rect.collidepoint(event.pos):
                        if reset_to_defaults():
                            show_message("Settings reset to defaults!")
                        else:
                            show_message("Reset cancelled.")
                    elif trail_checkbox.collidepoint(event.pos):
                        enable_trail = not enable_trail
                    elif fade_checkbox.collidepoint(event.pos):
                        trail_fade = not trail_fade
                    elif main_grid_checkbox.collidepoint(event.pos):
                        enable_main_grid = not enable_main_grid
                    elif mini_grid_checkbox.collidepoint(event.pos):
                        enable_mini_grid = not enable_mini_grid
                    elif mini_screen_checkbox.collidepoint(event.pos):
                        enable_mini_screen = not enable_mini_screen
                    elif zoom_checkbox.collidepoint(event.pos):
                        minimap_zoom = not minimap_zoom
                    elif borderless_checkbox.collidepoint(event.pos):
                        set_borderless(not borderless)
                    elif topmost_checkbox.collidepoint(event.pos):
                        always_on_top = not always_on_top
                        apply_always_on_top()
                    elif hide_ui_checkbox.collidepoint(event.pos):
                        toggle_overlay_mode(False)
                    elif hide_all_checkbox.collidepoint(event.pos):
                        toggle_overlay_mode(True)
                    elif region_mode_rect.collidepoint(event.pos):
                        region_mode = (region_mode + (1 if event.pos[0] >= region_mode_rect.centerx else -1)) % len(REGION_MODES)
                        set_view()

                    # Sliders: the drawn track plus the handle's overhang; a click sets the value
                    for name, slider in (("trail", trail_length_slider), ("smooth", smooth_factor_slider),
                                         ("thickness", trail_thickness_slider), ("active_area_thickness", area_thickness_slider)):
                        if slider.inflate(10, 10).collidepoint(event.pos):
                            slider_grabbed = name
                            drag_slider(event.pos[0])
                            break

                    # Handle input boxes (RGB + Active Area)
                    input_clicked = False
                    # Deactivate all inputs before checking for new activation
                    deactivate_all_inputs()
                    # Color preview clicks (open color picker)
                    if not input_clicked and cursor_color_preview_rect and cursor_color_preview_rect.collidepoint(event.pos):
                        color_picker_open = True
                        color_picker_type = "cursor"
                        color_picker_temp_values = cursor_rgb_values.copy()
                        h, s, v = rgb_to_hsv(*cursor_rgb_values)
                        color_picker_hue = h
                        color_picker_saturation = s
                        color_picker_value = v
                        input_clicked = True
                    elif not input_clicked and trail_color_preview_rect and trail_color_preview_rect.collidepoint(event.pos):
                        color_picker_open = True
                        color_picker_type = "trail"
                        color_picker_temp_values = trail_rgb_values.copy()
                        h, s, v = rgb_to_hsv(*trail_rgb_values)
                        color_picker_hue = h
                        color_picker_saturation = s
                        color_picker_value = v
                        input_clicked = True
                    elif not input_clicked and active_area_color_preview_rect and active_area_color_preview_rect.collidepoint(event.pos):
                        color_picker_open = True
                        color_picker_type = "active_area"
                        color_picker_temp_values = active_area_rgb_values.copy()
                        h, s, v = rgb_to_hsv(*active_area_rgb_values)
                        color_picker_hue = h
                        color_picker_saturation = s
                        color_picker_value = v
                        input_clicked = True
                    elif not input_clicked and background_color_preview_rect and background_color_preview_rect.collidepoint(event.pos):
                        color_picker_open = True
                        color_picker_type = "background"
                        color_picker_temp_values = background_rgb_values.copy()
                        h, s, v = rgb_to_hsv(*background_rgb_values)
                        color_picker_hue = h
                        color_picker_saturation = s
                        color_picker_value = v
                        input_clicked = True

                    # Hex input boxes (use same system as Active Area input):
                    if cursor_hex_input_rect and cursor_hex_input_rect.collidepoint(event.pos):
                        active_input = "cursor_hex"
                        input_text = rgb_to_hex(*cursor_rgb_values)
                        input_clicked = True
                    elif trail_hex_input_rect and trail_hex_input_rect.collidepoint(event.pos):
                        active_input = "trail_hex"
                        input_text = rgb_to_hex(*trail_rgb_values)
                        input_clicked = True
                    elif rectangle_hex_input_rect and rectangle_hex_input_rect.collidepoint(event.pos):
                        active_input = "rectangle_hex"
                        input_text = rgb_to_hex(*active_area_rgb_values)
                        input_clicked = True
                    elif background_hex_input_rect and background_hex_input_rect.collidepoint(event.pos):
                        active_input = "background_hex"
                        input_text = rgb_to_hex(*background_rgb_values)
                        input_clicked = True
                    # Active Area inputs (only if unlocked)
                    if not input_clicked and not active_area_locked:
                        for i in range(5):
                            if active_area_inputs[i].collidepoint(event.pos):
                                active_input = f"active_{i}"
                                input_text = str(active_area_values[i])
                                input_clicked = True
                                break
                    # Tracking region inputs, those the mode uses
                    if not input_clicked:
                        for i in region_fields():
                            if region_inputs[i].collidepoint(event.pos):
                                active_input = f"region_{i}"
                                input_text = f"{region_values[i]:g}"
                                input_clicked = True
                                break

                    # Check for protection shield clicks
                    if not input_clicked and active_area_locked:
                        # Check if click is in the active area section
                        if active_area_section.collidepoint(event.pos):
                            active_area_unlock_clicks += 1
                            active_area_unlock_timer = pygame.time.get_ticks()
                            
                            # Check if 3 clicks reached
                            if active_area_unlock_clicks >= 3:
                                active_area_locked = False
                                active_area_unlock_clicks = 0
                                show_message("Active area unlocked! Use with caution.", 2000)
                            else:
                                show_message(f"Click {3 - active_area_unlock_clicks} more times to unlock", 1000)
                    # If no input box was clicked, clear all inputs
                    if not input_clicked:
                        deactivate_all_inputs()
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:  # Left click release
                slider_grabbed = False
                window_drag = None
                # Stop color picker dragging
                color_picker_dragging = False
                color_picker_drag_type = None
        
        elif event.type == pygame.MOUSEMOTION:
            if slider_grabbed:
                drag_slider(event.pos[0])
            
            # Handle color picker dragging
            if color_picker_dragging and color_picker_open:
                popup_elements = draw_color_picker_popup()
                
                if color_picker_drag_type == "wheel":
                    wheel_center = popup_elements['wheel_center']
                    wheel_radius = popup_elements['wheel_radius']
                    distance = ((event.pos[0] - wheel_center[0])**2 + (event.pos[1] - wheel_center[1])**2)**0.5
                    
                    if distance <= wheel_radius:
                        # Calculate hue and saturation from drag position
                        dx = event.pos[0] - wheel_center[0]
                        dy = event.pos[1] - wheel_center[1]
                        angle = math.degrees(math.atan2(dy, dx)) % 360
                        saturation = min(100, (distance / wheel_radius) * 100)
                        
                        color_picker_hue = angle
                        color_picker_saturation = saturation
                        color_picker_temp_values = hsv_to_rgb(color_picker_hue, color_picker_saturation, color_picker_value)
                
                elif color_picker_drag_type == "value_slider":
                    vs_x, vs_y, vs_w, vs_h = popup_elements['value_slider']
                    if vs_y <= event.pos[1] <= vs_y + vs_h:
                        value = 100 - ((event.pos[1] - vs_y) / vs_h) * 100
                        color_picker_value = max(0, min(100, value))
                        color_picker_temp_values = hsv_to_rgb(color_picker_hue, color_picker_saturation, color_picker_value)
                
                elif color_picker_drag_type in ["r_slider", "g_slider", "b_slider"]:
                    slider_rect = popup_elements[color_picker_drag_type]
                    if slider_rect.x <= event.pos[0] <= slider_rect.x + slider_rect.width:
                        # Calculate value from drag position
                        rel_x = (event.pos[0] - slider_rect.x) / slider_rect.width
                        value = int(rel_x * 255)
                        value = max(0, min(255, value))
                        
                        if color_picker_drag_type == 'r_slider':
                            color_picker_temp_values[0] = value
                        elif color_picker_drag_type == 'g_slider':
                            color_picker_temp_values[1] = value
                        elif color_picker_drag_type == 'b_slider':
                            color_picker_temp_values[2] = value
                        
                        # Update HSV values
                        h, s, v = rgb_to_hsv(*color_picker_temp_values)
                        color_picker_hue = h
                        color_picker_saturation = s
                        color_picker_value = v
        
        elif event.type == pygame.KEYDOWN:
            # Handle color picker popup keyboard shortcuts
            if color_picker_open:
                if event.key == pygame.K_ESCAPE:
                    color_picker_open = False
                    color_picker_type = None
                elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                    # Apply the color
                    if color_picker_type == "cursor":
                        cursor_rgb_values = color_picker_temp_values.copy()
                        cursor_color = tuple(cursor_rgb_values)
                    elif color_picker_type == "trail":
                        trail_rgb_values = color_picker_temp_values.copy()
                        trail_color = tuple(trail_rgb_values)
                    elif color_picker_type == "active_area":
                        active_area_rgb_values = color_picker_temp_values.copy()
                        active_area_color = tuple(active_area_rgb_values)
                    elif color_picker_type == "background":
                        background_rgb_values = color_picker_temp_values.copy()
                        BACKGROUND_COLOR = tuple(background_rgb_values)
                    color_picker_open = False
                    color_picker_type = None
            
            elif active_input is not None:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                    # Apply the value; Tab then moves to the next field
                    input_error = False
                    error_message = ""
                    
                    # Handle hex inputs first (before trying to convert to int)
                    if active_input.endswith("_hex"):
                        if not input_text.strip():
                            # If hex input is empty, use default black
                            if active_input == "cursor_hex":
                                cursor_rgb_values = [0, 0, 0]
                                cursor_color = (0, 0, 0)
                            elif active_input == "trail_hex":
                                trail_rgb_values = [0, 0, 0]
                                trail_color = (0, 0, 0)
                            elif active_input == "rectangle_hex":
                                active_area_rgb_values = [0, 0, 0]
                                active_area_color = (0, 0, 0)
                            elif active_input == "background_hex":
                                background_rgb_values = [0, 0, 0]
                                BACKGROUND_COLOR = (0, 0, 0)
                        else:
                            hex_str = input_text.strip().lstrip('#')
                            if len(hex_str) == 6:
                                try:
                                    r = int(hex_str[0:2], 16)
                                    g = int(hex_str[2:4], 16)
                                    b = int(hex_str[4:6], 16)
                                    if active_input == "cursor_hex":
                                        cursor_rgb_values = [r, g, b]
                                        cursor_color = (r, g, b)
                                    elif active_input == "trail_hex":
                                        trail_rgb_values = [r, g, b]
                                        trail_color = (r, g, b)
                                    elif active_input == "rectangle_hex":
                                        active_area_rgb_values = [r, g, b]
                                        active_area_color = (r, g, b)
                                    elif active_input == "background_hex":
                                        background_rgb_values = [r, g, b]
                                        BACKGROUND_COLOR = (r, g, b)
                                except ValueError:
                                    input_error = True
                                    error_message = "Invalid hex color"
                            else:
                                input_error = True
                                error_message = "Hex color must be 6 characters"
                    else:
                        # Handle regular numeric inputs
                        try:
                            if not input_text.strip():
                                # If input is empty, use default value based on input type
                                if active_input.startswith("cursor"):
                                    index = int(active_input.split("_")[1])
                                    cursor_rgb_values[index] = 0  # Default RGB value
                                    cursor_color = tuple(cursor_rgb_values)
                                elif active_input.startswith("trail"):
                                    index = int(active_input.split("_")[1])
                                    trail_rgb_values[index] = 0  # Default RGB value
                                    trail_color = tuple(trail_rgb_values)
                                elif active_input.startswith("active"):
                                    index = int(active_input.split("_")[1])
                                    active_area_values[index] = 0 if index == 4 else 1  # Default minimum value
                                    active_area_x, active_area_y, active_area_width, active_area_height, active_area_rotation = active_area_values
                                elif active_input.startswith("region"):
                                    index = int(active_input.split("_")[1])
                                    region_values[index] = REGION_DEFAULTS[index]
                                    set_view()
                            else:
                                value = float(input_text) if active_input.startswith(("active", "region")) else int(input_text)

                                if active_input.startswith("cursor"):
                                    index = int(active_input.split("_")[1])
                                    # Clamp RGB values to 0-255 range
                                    clamped_value = max(0, min(255, value))
                                    cursor_rgb_values[index] = clamped_value
                                    cursor_color = tuple(cursor_rgb_values)

                                elif active_input.startswith("trail"):
                                    index = int(active_input.split("_")[1])
                                    # Clamp RGB values to 0-255 range
                                    clamped_value = max(0, min(255, value))
                                    trail_rgb_values[index] = clamped_value
                                    trail_color = tuple(trail_rgb_values)

                                elif active_input.startswith("active"):
                                    index = int(active_input.split("_")[1])
                                    if value < 1 and index != 4:  # rotation takes any angle
                                        input_error = True
                                        error_message = "Active area values must be at least 1"
                                    else:
                                        active_area_values[index] = value
                                        active_area_x, active_area_y, active_area_width, active_area_height, active_area_rotation = active_area_values

                                elif active_input.startswith("region"):
                                    index = int(active_input.split("_")[1])
                                    low, high = REGION_LIMITS[index]
                                    if not low <= value <= high:
                                        input_error = True
                                        error_message = f"{REGION_LABELS[index]}: {low:g} to {high:g}"
                                    else:
                                        region_values[index] = value
                                        set_view()

                        except ValueError:
                            input_error = True
                            error_message = "Please enter a valid number"
                    
                    # Only clear if no error
                    if input_error:
                        pass
                    elif event.key == pygame.K_TAB:
                        order = tab_order()
                        tab_step = -1 if event.mod & pygame.KMOD_SHIFT else 1
                        active_input = order[(order.index(active_input) + tab_step) % len(order)] if active_input in order else order[0]
                        if active_input.endswith("_hex"):
                            input_text = rgb_to_hex(*{"cursor_hex": cursor_rgb_values, "trail_hex": trail_rgb_values,
                                                      "rectangle_hex": active_area_rgb_values,
                                                      "background_hex": background_rgb_values}[active_input])
                        elif active_input.startswith("region"):
                            input_text = f"{region_values[int(active_input.split('_')[1])]:g}"
                        else:
                            input_text = str(active_area_values[int(active_input.split("_")[1])])
                    else:
                        active_input = None
                        input_text = ""

                elif event.key == pygame.K_ESCAPE:
                    # Cancel editing - restore original value
                    active_input = None
                    input_text = ""
                    input_error = False
                    error_message = ""

                elif event.key == pygame.K_BACKSPACE:
                    # Start backspace hold
                    backspace_held = True
                    backspace_start_time = pygame.time.get_ticks()
                    
                    # Perform backspace action
                    if active_input.endswith("_hex") and len(input_text) > 1:
                        if input_text.startswith('#'):
                            input_text = input_text[:-1]
                        else:
                            input_text = '#' + input_text[1:-1]
                    else:
                        input_text = input_text[:-1]
                    
                    # Update color in real-time for RGB inputs
                    if active_input.startswith("cursor") or active_input.startswith("trail"):
                        update_color_in_realtime()
                elif event.unicode:
                    # Handle hex input (only allow hex characters after '#')
                    if active_input.endswith("_hex"):
                        if len(input_text) < 7 and event.unicode.upper() in '0123456789ABCDEF':
                            if not input_text.startswith('#'):
                                input_text = '#' + input_text
                            if len(input_text) < 7:
                                input_text += event.unicode.upper()
                    # Handle regular numeric input
                    elif event.unicode.isdigit():
                        input_text += event.unicode
                        # Update color in real-time for RGB inputs
                        if active_input.startswith("cursor") or active_input.startswith("trail"):
                            update_color_in_realtime()
                    # Area and region values take decimals; rotation may be negative
                    elif active_input.startswith(("active", "region")) and (
                            (event.unicode == "." and "." not in input_text)
                            or (event.unicode == "-" and active_input == "active_4" and not input_text)):
                        input_text += event.unicode
        
        elif event.type == pygame.KEYUP:
            # Stop backspace hold when key is released
            if event.key == pygame.K_BACKSPACE:
                backspace_held = False

            # --- Tooltip overlay toggle ---
            if event.key == pygame.K_LALT or event.key == pygame.K_RALT:
                tooltip_active = not tooltip_active
            # Handle tooltip options if active
            if tooltip_active:
                if event.key == pygame.K_1:
                    set_borderless(not borderless)
                    tooltip_active = False
                elif event.key == pygame.K_2:
                    toggle_overlay_mode(False)  # Option 2: Hide UI (but keep minimap)
                    tooltip_active = False
                elif event.key == pygame.K_3:
                    toggle_overlay_mode(True)  # Option 3: Hide UI + minimap
                    tooltip_active = False



            # Add input state for all color hex inputs
            # cursor_hex_input_active = False
            # cursor_hex_input_text = ""
            # cursor_hex_input_rect = None

            # trail_hex_input_active = False
            # trail_hex_input_text = ""
            # trail_hex_input_rect = None

            # rectangle_hex_input_active = False
            # rectangle_hex_input_text = ""
            # rectangle_hex_input_rect = None

            # background_hex_input_active = False
            # background_hex_input_text = ""
            # background_hex_input_rect = None





sampler_stop.set()
sampler.join(1)
pygame.quit()