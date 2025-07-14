import pygame
import pyautogui
import numpy as np
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

# Now add the argument parsing
parser = argparse.ArgumentParser(description='Cursor Tracking Tool')
parser.add_argument('-console', action='store_true', help='Show console window')
args = parser.parse_args()

# Hide console if not using -console flag and running as exe
if not args.console and getattr(sys, 'frozen', False):
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# Note: For better window focus management, install pywin32: pip install pywin32

# Initialize pygame
pygame.init()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

icon_path = resource_path("cursor_logo.png")
icon = pygame.image.load(icon_path)
pygame.display.set_icon(icon)

# Get screen size & set window size
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()
WIN_WIDTH, WIN_HEIGHT = 800, 600
SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT = 200, 150  # Mini display

# Create main & small windows
screen = pygame.display.set_mode((WIN_WIDTH, WIN_HEIGHT))
small_screen = pygame.Surface((SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT), pygame.SRCALPHA)
pygame.display.set_caption("Simple Cursor Tracking")

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
smooth_factor = 0.3

# Grid settings
GRID_SPACING = 20  # Grid spacing

# Get initial position
prev_x, prev_y = pyautogui.position()

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

# Color picker drag state
color_picker_dragging = False
color_picker_drag_type = None  # "wheel", "value_slider", "r_slider", "g_slider", "b_slider"

# Color preview rectangles for click detection
cursor_color_preview_rect = None
trail_color_preview_rect = None
active_area_color_preview_rect = None
background_color_preview_rect = None

background_hex_input_active = False

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
    title_text = f"{color_picker_type.title() if color_picker_type else 'Color'} Color Picker"
    title_surface = font.render(title_text, True, BUTTON_TEXT_COLOR)
    title_rect = title_surface.get_rect(centerx=popup_x + popup_width//2, y=popup_y + 10)
    screen.blit(title_surface, title_rect)
    
    # Color wheel area (simplified as a gradient circle)
    wheel_center_x = popup_x + 120
    wheel_center_y = popup_y + 120
    wheel_radius = 80
    
    # Draw color wheel (simplified version)
    for angle in range(0, 360, 5):
        for radius in range(0, wheel_radius, 2):
            h = angle
            s = (radius / wheel_radius) * 100
            v = color_picker_value
            rgb = hsv_to_rgb(h, s, v)
            
            x = wheel_center_x + int(radius * np.cos(np.radians(angle)))
            y = wheel_center_y + int(radius * np.sin(np.radians(angle)))
            
            if 0 <= x < WIN_WIDTH and 0 <= y < WIN_HEIGHT:
                pygame.draw.circle(screen, rgb, (x, y), 1)
    
    # Draw wheel border
    pygame.draw.circle(screen, (200, 200, 200), (wheel_center_x, wheel_center_y), wheel_radius, 2)
    
    # Draw current selection indicator on wheel
    indicator_x = wheel_center_x + int((color_picker_saturation / 100) * wheel_radius * np.cos(np.radians(color_picker_hue)))
    indicator_y = wheel_center_y + int((color_picker_saturation / 100) * wheel_radius * np.sin(np.radians(color_picker_hue)))
    
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

def try_get_tablet_info(settings):
    # Try Devices first
    for device in settings.get("Devices", []):
        if "Area" in device:
            area = device["Area"]
            name = device.get("Tablet") or device.get("Name") or device.get("Model") or "Unknown"
            return name, area, None, None
    # Try Profiles
    for profile in settings.get("Profiles", []):
        name = profile.get("Tablet") or profile.get("Name") or profile.get("Model") or "Unknown"
        area = profile.get("Area")
        display = profile.get("Display")
        # Prefer direct Area/Display if present
        if area or display:
            return name, area, display, None
        # Otherwise, look for AbsoluteModeSettings at the same level as Filters
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
# Active area from settings
active_area_x = 0
active_area_y = 0
active_area_width = 216  # Default fallback
active_area_height = 135  # Default fallback

# Replace the settings loading logic with:
settings_path = prompt_for_settings_selection()

# Restore focus to Pygame window after initial settings selection
try:
    import win32gui
    import win32con
    # Find the Pygame window and bring it to front
    hwnd = win32gui.FindWindow(None, "Simple Cursor Tracking")
    if hwnd:
        win32gui.SetForegroundWindow(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
except ImportError:
    # If win32gui is not available, try alternative method
    try:
        pygame.display.set_caption("Simple Cursor Tracking")
        pygame.display.update()
    except:
        pass

if not settings_path:
    print("No settings file available. Using default values.")
    tablet_name = "Unknown"
    tablet_width = 216
    tablet_height = 135
else:
    print(f"Reading settings from: {settings_path}")
    try:
        with open(settings_path, "r") as f:
            settings = json.load(f)
        tablet_name, area, display, abs_tablet = try_get_tablet_info(settings)
        if area:
            tablet_width = area[2] - area[0]
            tablet_height = area[3] - area[1]
            print(f"Tablet area: {area}")
            print(f"Tablet width: {tablet_width}, Tablet height: {tablet_height}")
        elif abs_tablet:
            tablet_width = abs_tablet.get("Width")
            tablet_height = abs_tablet.get("Height")
            print(f"Tablet (from AbsoluteModeSettings): {abs_tablet}")
            print(f"Tablet width: {tablet_width}, Tablet height: {tablet_height}")
        else:
            print("Tablet area not found, using default size.")

        # Extract and display active area from AbsoluteModeSettings
        active_area_found = False
        for profile in settings.get("Profiles", []):
            abs_mode = profile.get("AbsoluteModeSettings")
            if abs_mode and "Tablet" in abs_mode:
                tab = abs_mode["Tablet"]
                if all(k in tab for k in ("Width", "Height", "X", "Y")):
                    active_area_x = tab["X"]
                    active_area_y = tab["Y"]
                    active_area_width = tab["Width"]
                    active_area_height = tab["Height"]
                    print(f"Active Area: X={active_area_x}, Y={active_area_y}, Width={active_area_width}, Height={active_area_height}")
                    active_area_found = True
                    break
        
        if not active_area_found:
            print("Active area (AbsoluteModeSettings.Tablet) not found in settings.")

        if display:
            display_width = display.get("Width")
            display_height = display.get("Height")
            print(f"Display: {display}")
            print(f"Display width: {display_width}, Display height: {display_height}")
        elif abs_tablet:
            print("Display area not found, but AbsoluteModeSettings Tablet found.")
        else:
            print("Display area not found.")
    except Exception as e:
        print(f"Failed to read OpenTabletDriver area: {e}")
        tablet_name = "Unknown"
        tablet_width = 216
        tablet_height = 135

# After tablet_name is detected, add this logic:
print(f"Final tablet model/name: {tablet_name}", flush=True)
# Separate brand and model
parts = tablet_name.split()
if len(parts) >= 2:
    brand = parts[0]
    model = ' '.join(parts[1:])
    print(f"Brand: {brand}, Model: {model}", flush=True)
    # Load dimensions from config
    tablet_width, tablet_height = get_tablet_dimensions_from_config(tablet_name)
    if tablet_width is None or tablet_height is None:
        print("Using default tablet size (216x135)")
        tablet_width, tablet_height = 216, 135
else:
    print(f"Tablet name '{tablet_name}' is not in expected 'Brand Model' format.")
    tablet_width, tablet_height = 216, 135

print(f"Final tablet width: {tablet_width}, height: {tablet_height}", flush=True)
if display_width is not None and display_height is not None:
    print(f"Final display width: {display_width}, height: {display_height}", flush=True)
else:
    print("[HINT] Display area not found in settings.", flush=True)

if tablet_width == 216 and tablet_height == 135:
    print("[HINT] Tablet area not found in settings. Using default tablet area (216x135).", flush=True)

# Active Area Input Boxes - these now represent the ACTIVE area from settings
active_area_inputs = [pygame.Rect(0, 0, 80, 30) for _ in range(4)]
# Use active area values from settings as defaults
active_area_values = [active_area_x, active_area_y, active_area_width, active_area_height]  # [left, top, width, height]

if active_area_values[2] == 216 and active_area_values[3] == 135:
    print("[HINT] Active area is set to default (no settings found).", flush=True)

print(f"Active area width: {active_area_values[2]}, height: {active_area_values[3]}", flush=True)

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

def get_active_area_bounds():
    """Get the current active area bounds"""
    return {
        'left': active_area_values[0],
        'top': active_area_values[1], 
        'width': active_area_values[2],
        'height': active_area_values[3]
    }

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
        'active_area_color': active_area_rgb_values,
        'active_area_thickness': active_area_thickness,
        'background_color': background_rgb_values
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
    try:
        import win32gui
        import win32con
        # Find the Pygame window and bring it to front
        hwnd = win32gui.FindWindow(None, "Simple Cursor Tracking")
        if hwnd:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except ImportError:
        # If win32gui is not available, try alternative method
        try:
            pygame.display.set_caption("Simple Cursor Tracking")
            pygame.display.update()
        except:
            pass

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
    global background_rgb_values, BACKGROUND_COLOR
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
                try:
                    import win32gui
                    import win32con
                    # Find the Pygame window and bring it to front
                    hwnd = win32gui.FindWindow(None, "Simple Cursor Tracking")
                    if hwnd:
                        win32gui.SetForegroundWindow(hwnd)
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                except ImportError:
                    # If win32gui is not available, try alternative method
                    try:
                        pygame.display.set_caption("Simple Cursor Tracking")
                        pygame.display.update()
                    except:
                        pass
            else:
                # Automatic load: try to load the last used file first
                last_path = get_last_used_settings_path()
                if last_path and os.path.isfile(last_path):
                    print(f"Loading last used settings: {last_path}")
                    filepath = last_path
                else:
                    # Show file dialog if no last used file
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
                    try:
                        import win32gui
                        import win32con
                        # Find the Pygame window and bring it to front
                        hwnd = win32gui.FindWindow(None, "Simple Cursor Tracking")
                        if hwnd:
                            win32gui.SetForegroundWindow(hwnd)
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    except ImportError:
                        # If win32gui is not available, try alternative method
                        try:
                            pygame.display.set_caption("Simple Cursor Tracking")
                            pygame.display.update()
                        except:
                            pass
        
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
                
                # Load active area styling
                active_area_rgb_values = settings.get('active_area_color', active_area_rgb_values)
                active_area_thickness = settings.get('active_area_thickness', active_area_thickness)
                
                # Load background color
                background_rgb_values = settings.get('background_color', background_rgb_values)
                BACKGROUND_COLOR = tuple(background_rgb_values)
                
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
    global background_rgb_values, BACKGROUND_COLOR
    
    # Show confirmation dialog
    root = tk.Tk()
    root.withdraw()
    result = messagebox.askyesno(
        "Reset to Defaults",
        "Are you sure you want to reset all settings to their default values?\n\n"
        "This will reset:\n"
        "• Cursor color, trail color, rectangle color, background color\n"
        "• Rectangle thickness, trail length, smoothness, thickness\n"
        "• All checkboxes to their default states\n\n"
        "This action cannot be undone."
    )
    
    # Restore focus to Pygame window after dialog
    try:
        import win32gui
        import win32con
        # Find the Pygame window and bring it to front
        hwnd = win32gui.FindWindow(None, "Simple Cursor Tracking")
        if hwnd:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except ImportError:
        # If win32gui is not available, try alternative method
        try:
            pygame.display.set_caption("Simple Cursor Tracking")
            pygame.display.update()
        except:
            pass
    
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
        
        # Reset active area values to defaults (these will be calculated based on tablet dimensions)
        # The active area values are set dynamically based on tablet info, so we'll keep current values
        # but reset the styling
        
        print("All settings reset to defaults")
        return True
    else:
        print("Reset cancelled by user")
        return False

def show_message(message, duration=500):
    message_surface = font.render(message, True, BUTTON_TEXT_COLOR)
    message_rect = message_surface.get_rect(center=(WIN_WIDTH//2, WIN_HEIGHT - 100))
    screen.blit(message_surface, message_rect)
    pygame.display.update()
    pygame.time.wait(duration)

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
    return checkbox_rect

def draw_button(screen, text, rect, hover):
    button_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    button_surface.fill(BUTTON_HOVER_COLOR if hover else BUTTON_COLOR)
    button_surface.set_alpha(150)
    
    button_text = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = button_text.get_rect(center=(rect.width//2, rect.height//2))
    button_surface.blit(button_text, text_rect)
    
    screen.blit(button_surface, rect)

def catmull_rom_spline(p0, p1, p2, p3, num_points=10):
    """Generates a smooth Catmull-Rom spline through points."""
    p0, p1, p2, p3 = map(np.array, [p0, p1, p2, p3])
    t = np.linspace(0, 1, num_points)
    t2 = t**2
    t3 = t**3
    basis = np.array([
        -t3 + 2*t2 - t,
        3*t3 - 5*t2 + 2,
        -3*t3 + 4*t2 + t,
        t3 - t2
    ]).T * 0.5
    result = basis @ np.vstack([p0, p1, p2, p3])
    return result.astype(int)

def draw_input_box(rect, value, is_active, label_text="", placeholder=""):
    """Draw a user-friendly input box with hover effects, borders, and cursor"""
    mouse_pos = pygame.mouse.get_pos()
    is_hovered = rect.collidepoint(mouse_pos)
    
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
    
    # Clip text if it's too long
    if text_surface.get_width() > rect.width - 16:
        # Create a clipped surface
        clipped_surface = pygame.Surface((rect.width - 16, text_surface.get_height()))
        clipped_surface.fill(box_color)
        clipped_surface.blit(text_surface, (0, 0))
        screen.blit(clipped_surface, (text_x, text_y))
    else:
        screen.blit(text_surface, (text_x, text_y))
    
    # Draw cursor if active
    if is_active:
        if input_text != "":
            cursor_x = text_x + font.render(input_text, True, text_color).get_width()
        else:
            cursor_x = text_x  # Cursor at start when input is empty
        cursor_y = text_y
        cursor_height = text_surface.get_height()
        
        # Blinking cursor effect (simple implementation)
        if pygame.time.get_ticks() % 1000 < 500:
            pygame.draw.line(screen, INPUT_TEXT_COLOR, 
                           (cursor_x, cursor_y), 
                           (cursor_x, cursor_y + cursor_height), 2)
    
    # Draw hover tooltip
    if is_hovered and not is_active:
        tooltip_text = "Click to edit"
        tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
        tooltip_rect = tooltip_surface.get_rect()
        tooltip_rect.topleft = (rect.x, rect.y - 25)
        
        # Draw tooltip background
        tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                               tooltip_rect.width + 10, tooltip_rect.height + 4)
        pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
        pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
        screen.blit(tooltip_surface, tooltip_rect)

def draw_color_section(y_offset, title, rgb_values, rgb_inputs, is_cursor=True, hex_input_active=False, hex_input_text="", hex_input_rect=None):
    # Draw section title
    section_title = font.render(title, True, BUTTON_TEXT_COLOR)
    screen.blit(section_title, (50, y_offset))
    
    # Draw color preview (clickable)
    preview_rect = pygame.Rect(50, y_offset + 25, 80, 40)
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

def draw_slider(x, y, width, value, min_val, max_val, label):
    # Draw slider label
    label_text = font.render(f"{label}: {value}", True, BUTTON_TEXT_COLOR)
    screen.blit(label_text, (x, y - 20))
    
    # Draw slider track
    slider_rect = pygame.Rect(x, y, width, SLIDER_HEIGHT)
    pygame.draw.rect(screen, SLIDER_COLOR, slider_rect)
    
    # Calculate and draw slider handle
    handle_pos = x + (value - min_val) * width / (max_val - min_val)
    handle_rect = pygame.Rect(handle_pos - 5, y - 5, 10, SLIDER_HEIGHT + 10)
    
    # Highlight if mouse is over handle
    mouse_pos = pygame.mouse.get_pos()
    if handle_rect.collidepoint(mouse_pos) or slider_grabbed:
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
    """Draw a thick line with rounded caps for smooth connections"""
    if thickness <= 1:
        pygame.draw.aaline(surface, color, start, end)
        return
    # Draw the main line
    pygame.draw.line(surface, color, start, end, thickness)
    # Draw rounded caps at both ends
    radius = thickness // 2
    pygame.draw.circle(surface, color, (int(start[0]), int(start[1])), radius)
    pygame.draw.circle(surface, color, (int(end[0]), int(end[1])), radius)

def ensure_trail_continuity(trail, max_gap_distance=10):
    """Fill gaps in trail by interpolating missing points"""
    if len(trail) < 2:
        return trail
    continuous_trail = [trail[0]]
    for i in range(1, len(trail)):
        prev_point = continuous_trail[-1]
        current_point = trail[i]
        dx = current_point[0] - prev_point[0]
        dy = current_point[1] - prev_point[1]
        distance = math.sqrt(dx*dx + dy*dy)
        if distance > max_gap_distance:
            num_interpolated = int(distance / max_gap_distance)
            for j in range(1, num_interpolated + 1):
                t = j / (num_interpolated + 1)
                interpolated_x = prev_point[0] + dx * t
                interpolated_y = prev_point[1] + dy * t
                continuous_trail.append((interpolated_x, interpolated_y))
        continuous_trail.append(current_point)
    return continuous_trail

def render_trail(screen, trail, trail_color, current_thickness, enable_trail=True, trail_fade=True):
    """
    Updated trail rendering with comprehensive improvements
    """
    if not enable_trail or len(trail) < 2:
        return
    # Ensure trail continuity
    continuous_trail = ensure_trail_continuity(trail, max_gap_distance=10)
    # Primary rendering: Draw lines between all consecutive points
    for i in range(len(continuous_trail) - 1):
        if trail_fade:
            fade = i / len(continuous_trail)
            current_color = [int(c * fade) for c in trail_color]
        else:
            current_color = trail_color
        # Draw main connection line
        draw_thick_line_with_caps(screen, current_color, 
                                continuous_trail[i], continuous_trail[i + 1], 
                                current_thickness)
    # Secondary rendering: Apply spline smoothing for curved sections
    if len(continuous_trail) > 3:
        for i in range(1, len(continuous_trail) - 2):
            p0, p1, p2, p3 = continuous_trail[i - 1], continuous_trail[i], continuous_trail[i + 1], continuous_trail[i + 2]
            smooth_points = catmull_rom_spline(p0, p1, p2, p3, num_points=25)
            for j in range(len(smooth_points) - 1):
                if trail_fade:
                    fade = (i + j/25) / len(continuous_trail)
                    current_color = [int(c * fade) for c in trail_color]
                else:
                    current_color = trail_color
                # Use anti-aliased lines for smooth curves
                pygame.draw.aaline(screen, current_color, smooth_points[j], smooth_points[j + 1], current_thickness)
                # Add connection circles for perfect continuity
                radius = max(1, current_thickness // 2)
                pygame.draw.circle(screen, current_color, 
                                 (int(smooth_points[j][0]), int(smooth_points[j][1])), radius)

# Add this helper function near the top, after global variable definitions:
def deactivate_all_inputs():
    global active_input
    global cursor_hex_input_active, trail_hex_input_active, rectangle_hex_input_active, background_hex_input_active
    active_input = None
    cursor_hex_input_active = False
    trail_hex_input_active = False
    rectangle_hex_input_active = False
    background_hex_input_active = False

# Main game loop
while running:
    screen.fill(BACKGROUND_COLOR)
    small_screen.fill((10, 10, 10))

    # Get current mouse position and update trail
    mouse_x, mouse_y = pyautogui.position()
    
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

    # Get current active area bounds
    active_bounds = get_active_area_bounds()

    # Map screen coordinates to active area coordinates
    # Screen (0,0 to SCREEN_WIDTH,SCREEN_HEIGHT) maps to active area (0,0 to active_width,active_height)
    active_area_mouse_x = (mouse_x / SCREEN_WIDTH) * active_bounds['width']
    active_area_mouse_y = (mouse_y / SCREEN_HEIGHT) * active_bounds['height']

    # Calculate position within tablet area
    # Active area position + active area offset = tablet position
    tablet_mouse_x = active_area_mouse_x + active_bounds['left']
    tablet_mouse_y = active_area_mouse_y + active_bounds['top']

    # Scale to main window for display (active area fills entire window)
    scaled_x = int(active_area_mouse_x * (WIN_WIDTH / active_bounds['width']))
    scaled_y = int(active_area_mouse_y * (WIN_HEIGHT / active_bounds['height']))

    # Smooth movement
    prev_x += (scaled_x - prev_x) * current_smooth
    prev_y += (scaled_y - prev_y) * current_smooth

    # Add to trail with length limit
    trail.append((int(prev_x), int(prev_y)))
    while len(trail) > current_trail_length:
        trail.pop(0)

    mouse_pos = pygame.mouse.get_pos()

    if settings_open:
        # Hide mini screen when settings are open (regardless of toggle)
        mini_visible = False
        
        # Draw full screen modal
        screen.fill(MODAL_BG_COLOR)
        
        # Draw title
        title = font.render("Settings", True, BUTTON_TEXT_COLOR)
        title_rect = title.get_rect(centerx=WIN_WIDTH//2, y=20)
        screen.blit(title, title_rect)
        
        # Define layout constants
        left_margin = 50
        right_margin = WIN_WIDTH - 50
        section_spacing = 80
        item_spacing = 35
        checkbox_spacing = 25
        
        # Section 1: Colors (top left)
        y_offset = 80
        # Cursor Color
        cursor_color_preview_rect, cursor_hex_input_rect = draw_color_section(
            y_offset, "Cursor Color", cursor_rgb_values, cursor_rgb_inputs,
            True, active_input == "cursor_hex", input_text if active_input == "cursor_hex" else "", cursor_hex_input_rect)
        # Trail Color
        trail_color_preview_rect, trail_hex_input_rect = draw_color_section(
            y_offset + 70, "Trail Color", trail_rgb_values, trail_rgb_inputs,
            False, active_input == "trail_hex", input_text if active_input == "trail_hex" else "", trail_hex_input_rect)
        # Rectangle Color
        active_area_color_preview_rect = pygame.Rect(310, y_offset + 25, 80, 40)
        pygame.draw.rect(screen, active_area_color, active_area_color_preview_rect)
        pygame.draw.rect(screen, BUTTON_TEXT_COLOR, active_area_color_preview_rect, 2)
        rectangle_hex_value = rgb_to_hex(*active_area_rgb_values)
        is_rectangle_active = active_input == "rectangle_hex"
        if is_rectangle_active:
            display_text = input_text
            text_color = INPUT_TEXT_COLOR
        else:
            display_text = rectangle_hex_value
            text_color = INPUT_TEXT_COLOR
        
        # Make hex input box longer (120px instead of 70px)
        input_box_width = 120
        input_box_height = 30
        input_box_x = active_area_color_preview_rect.right + 10  # 10px margin to the right
        input_box_y = active_area_color_preview_rect.y + (active_area_color_preview_rect.height - input_box_height) // 2
        rectangle_hex_input_rect = pygame.Rect(input_box_x, input_box_y, input_box_width, input_box_height)
        
        # Use the same styling as Active Area inputs
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = rectangle_hex_input_rect.collidepoint(mouse_pos)
        
        # Determine box color based on state (same as draw_input_box)
        if is_rectangle_active and input_error:
            box_color = INPUT_BOX_ERROR_COLOR
            border_color = INPUT_BOX_ERROR_BORDER_COLOR
        elif is_rectangle_active:
            box_color = INPUT_BOX_ACTIVE_COLOR
            border_color = INPUT_BOX_ACTIVE_BORDER_COLOR
        elif is_hovered:
            box_color = INPUT_BOX_HOVER_COLOR
            border_color = INPUT_BOX_BORDER_COLOR
        else:
            box_color = INPUT_BOX_COLOR
            border_color = INPUT_BOX_BORDER_COLOR
        
        # Draw input box with border
        pygame.draw.rect(screen, box_color, rectangle_hex_input_rect)
        pygame.draw.rect(screen, border_color, rectangle_hex_input_rect, 2)
        
        # Add subtle shadow/glow effect for active input
        if is_rectangle_active:
            # Draw a subtle glow around the active input
            glow_rect = pygame.Rect(rectangle_hex_input_rect.x - 2, rectangle_hex_input_rect.y - 2, rectangle_hex_input_rect.width + 4, rectangle_hex_input_rect.height + 4)
            pygame.draw.rect(screen, (100, 150, 255, 50), glow_rect, 1)
        
        # Draw text left-aligned with padding (same as draw_input_box)
        text_x = rectangle_hex_input_rect.x + 8
        text_y = rectangle_hex_input_rect.y + (input_box_height - font.get_height()) // 2
        text_surface = font.render(display_text, True, text_color)
        screen.blit(text_surface, (text_x, text_y))
        
        # Draw cursor if active (same as draw_input_box)
        if is_rectangle_active:
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
        if is_hovered and not is_rectangle_active:
            tooltip_text = "Click to edit"
            tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
            tooltip_rect = tooltip_surface.get_rect()
            tooltip_rect.topleft = (rectangle_hex_input_rect.x, rectangle_hex_input_rect.y - 25)
            
            # Draw tooltip background
            tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                                   tooltip_rect.width + 10, tooltip_rect.height + 4)
            pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
            pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
            screen.blit(tooltip_surface, tooltip_rect)
        # Rectangle label
        color_label = font.render("Rectangle Color", True, BUTTON_TEXT_COLOR)
        screen.blit(color_label, (310, y_offset))
        
        # Add hover tooltip for rectangle color picker
        if active_area_color_preview_rect.collidepoint(mouse_pos):
            tooltip_text = "Click to use RGB selector"
            tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
            tooltip_rect = tooltip_surface.get_rect()
            tooltip_rect.topleft = (active_area_color_preview_rect.x, active_area_color_preview_rect.y - 25)
            
            # Draw tooltip background
            tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                                   tooltip_rect.width + 10, tooltip_rect.height + 4)
            pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
            pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
            screen.blit(tooltip_surface, tooltip_rect)
        
        # Background Color
        background_color_preview_rect = pygame.Rect(530, y_offset + 25, 80, 40)
        pygame.draw.rect(screen, background_rgb_values, background_color_preview_rect)
        pygame.draw.rect(screen, BUTTON_TEXT_COLOR, background_color_preview_rect, 2)
        bg_label = font.render("Background Color", True, BUTTON_TEXT_COLOR)
        screen.blit(bg_label, (530, y_offset))
        
        # Add hover tooltip for background color picker
        if background_color_preview_rect.collidepoint(mouse_pos):
            tooltip_text = "Click to use RGB selector"
            tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
            tooltip_rect = tooltip_surface.get_rect()
            tooltip_rect.topleft = (background_color_preview_rect.x, background_color_preview_rect.y - 25)
            
            # Draw tooltip background
            tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                                   tooltip_rect.width + 10, tooltip_rect.height + 4)
            pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
            pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
            screen.blit(tooltip_surface, tooltip_rect)
        # Background hex input box (move to the right of the preview)
        bg_hex_value = rgb_to_hex(*background_rgb_values)
        is_background_active = active_input == "background_hex"
        if is_background_active:
            display_text = input_text
            text_color = INPUT_TEXT_COLOR
        else:
            display_text = bg_hex_value
            text_color = INPUT_TEXT_COLOR
        
        # Make hex input box longer (120px instead of 70px)
        input_box_width = 120
        input_box_height = 30
        input_box_x = background_color_preview_rect.right + 10  # 10px margin to the right
        input_box_y = background_color_preview_rect.y + (background_color_preview_rect.height - input_box_height) // 2
        background_hex_input_rect = pygame.Rect(input_box_x, input_box_y, input_box_width, input_box_height)
        
        # Use the same styling as Active Area inputs
        mouse_pos = pygame.mouse.get_pos()
        is_hovered = background_hex_input_rect.collidepoint(mouse_pos)
        
        # Determine box color based on state (same as draw_input_box)
        if is_background_active and input_error:
            box_color = INPUT_BOX_ERROR_COLOR
            border_color = INPUT_BOX_ERROR_BORDER_COLOR
        elif is_background_active:
            box_color = INPUT_BOX_ACTIVE_COLOR
            border_color = INPUT_BOX_ACTIVE_BORDER_COLOR
        elif is_hovered:
            box_color = INPUT_BOX_HOVER_COLOR
            border_color = INPUT_BOX_BORDER_COLOR
        else:
            box_color = INPUT_BOX_COLOR
            border_color = INPUT_BOX_BORDER_COLOR
        
        # Draw input box with border
        pygame.draw.rect(screen, box_color, background_hex_input_rect)
        pygame.draw.rect(screen, border_color, background_hex_input_rect, 2)
        
        # Add subtle shadow/glow effect for active input
        if is_background_active:
            # Draw a subtle glow around the active input
            glow_rect = pygame.Rect(background_hex_input_rect.x - 2, background_hex_input_rect.y - 2, background_hex_input_rect.width + 4, background_hex_input_rect.height + 4)
            pygame.draw.rect(screen, (100, 150, 255, 50), glow_rect, 1)
        
        # Draw text left-aligned with padding (same as draw_input_box)
        text_x = background_hex_input_rect.x + 8
        text_y = background_hex_input_rect.y + (input_box_height - font.get_height()) // 2
        text_surface = font.render(display_text, True, text_color)
        screen.blit(text_surface, (text_x, text_y))
        
        # Draw cursor if active (same as draw_input_box)
        if is_background_active:
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
        if is_hovered and not is_background_active:
            tooltip_text = "Click to edit"
            tooltip_surface = font.render(tooltip_text, True, (200, 200, 200))
            tooltip_rect = tooltip_surface.get_rect()
            tooltip_rect.topleft = (background_hex_input_rect.x, background_hex_input_rect.y - 25)
            
            # Draw tooltip background
            tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                                   tooltip_rect.width + 10, tooltip_rect.height + 4)
            pygame.draw.rect(screen, (40, 40, 40), tooltip_bg)
            pygame.draw.rect(screen, (100, 100, 100), tooltip_bg, 1)
            screen.blit(tooltip_surface, tooltip_rect)

        # Rectangle Thickness (below color picker)
        thickness_label = font.render(f"Rectangle Thickness: {active_area_thickness}", True, BUTTON_TEXT_COLOR)
        screen.blit(thickness_label, (310, y_offset + 80))
        # Draw thickness slider (bigger and 1-5 range)
        thickness_slider_rect = pygame.Rect(310, y_offset + 105, 150, 15)
        pygame.draw.rect(screen, (80, 80, 80), thickness_slider_rect)
        # Calculate slider position (1-5 range)
        slider_pos = 310 + (active_area_thickness - 1) * (150 / 4)
        pygame.draw.circle(screen, (200, 200, 200), (int(slider_pos), y_offset + 112), 8)
        

        
        # Section 3: Trail Settings (middle left)
        y_offset = 220
        section_title = font.render("Trail Settings", True, BUTTON_TEXT_COLOR)
        screen.blit(section_title, (left_margin, y_offset))
        
        # Trail checkboxes
        trail_checkbox = draw_checkbox(left_margin, y_offset + 30, "Enable Cursor Trail", enable_trail)
        fade_checkbox = draw_checkbox(left_margin + 200, y_offset + 30, "Enable Trail Fade", trail_fade)
        
        # Trail sliders (increased spacing from checkboxes)
        slider_x = left_margin
        slider_y = y_offset + 90  # Increased from 70 to 90
        trail_length_slider, handle_rect = draw_slider(
            slider_x, slider_y, SLIDER_WIDTH, 
            current_trail_length, min_trail_length, max_trail_length_limit,
            "Trail Length"
        )
        
        slider_y = y_offset + 130  # Increased from 110 to 130
        smooth_factor_slider, _ = draw_slider(
            slider_x, slider_y, SLIDER_WIDTH,
            current_smooth, min_smooth, max_smooth,
            "Smoothness"
        )
        
        slider_y = y_offset + 170  # Increased from 150 to 170
        trail_thickness_slider, _ = draw_slider(
            slider_x, slider_y, SLIDER_WIDTH,
            current_thickness, min_thickness, max_thickness,
            "Trail Thickness"
        )
        
        # Section 4: Grid Settings (middle right)
        y_offset = 220
        section_title = font.render("Grid Settings", True, BUTTON_TEXT_COLOR)
        screen.blit(section_title, (right_margin - 200, y_offset))
        
        main_grid_checkbox = draw_checkbox(right_margin - 200, y_offset + 30, "Enable Main Grid", enable_main_grid)
        mini_grid_checkbox = draw_checkbox(right_margin - 200, y_offset + 55, "Enable Mini Grid", enable_mini_grid)
        mini_screen_checkbox = draw_checkbox(right_margin - 200, y_offset + 100, "Enable Mini Screen", enable_mini_screen)
        
        # Section 5: Active Area (bottom left)
        y_offset = 420
        section_title = font.render("Active Area (mm)", True, BUTTON_TEXT_COLOR)
        screen.blit(section_title, (left_margin, y_offset))
        
        # First row: Width, Height
        labels_row1 = ["Width:", "Height:"]
        for i in range(2):
            active_area_inputs[i+2].x = left_margin + 60 + i * 180  # Width (index 2), Height (index 3)
            active_area_inputs[i+2].y = y_offset + 30
            is_active = active_input == f"active_{i+2}"
            draw_input_box(active_area_inputs[i+2], active_area_values[i+2], is_active, labels_row1[i])
        
        # Second row: X, Y
        labels_row2 = ["X:", "Y:"]
        for i in range(2):
            active_area_inputs[i].x = left_margin + 60 + i * 180  # X (index 0), Y (index 1)
            active_area_inputs[i].y = y_offset + 70
            is_active = active_input == f"active_{i}"
            draw_input_box(active_area_inputs[i], active_area_values[i], is_active, labels_row2[i])
        

        
        # Draw protection shield overlay if active area is locked
        if active_area_locked:
            # Create a semi-transparent grey overlay covering the entire active area section
            shield_rect = pygame.Rect(left_margin - 10, y_offset - 10, 400, 120)  # Covers the entire section
            
            # Draw semi-transparent grey background
            shield_surface = pygame.Surface((shield_rect.width, shield_rect.height), pygame.SRCALPHA)
            shield_surface.fill((80, 80, 80, 180))  # Grey with alpha
            screen.blit(shield_surface, shield_rect)
            
            # Draw border
            pygame.draw.rect(screen, (120, 120, 120), shield_rect, 2)
            
            # Draw lock icon or warning text
            warning_text = "⚠️ PROTECTED AREA"
            warning_surface = font.render(warning_text, True, (200, 200, 200))
            warning_rect = warning_surface.get_rect(centerx=shield_rect.centerx, y=shield_rect.centery - 15)
            screen.blit(warning_surface, warning_rect)
            
            # Draw unlock instruction
            unlock_text = f"Click {3 - active_area_unlock_clicks} more times to unlock"
            unlock_surface = font.render(unlock_text, True, (150, 150, 150))
            unlock_rect = unlock_surface.get_rect(centerx=shield_rect.centerx, y=shield_rect.centery + 15)
            screen.blit(unlock_surface, unlock_rect)
            
            # Check for hover and show tooltip
            mouse_pos = pygame.mouse.get_pos()
            if shield_rect.collidepoint(mouse_pos):
                tooltip_text = "⚠️ WARNING: Changing active area may break tablet functionality!"
                tooltip_surface = font.render(tooltip_text, True, (255, 200, 200))
                tooltip_rect = tooltip_surface.get_rect()
                tooltip_rect.topleft = (shield_rect.x, shield_rect.y - 40)
                
                # Draw tooltip background
                tooltip_bg = pygame.Rect(tooltip_rect.x - 5, tooltip_rect.y - 2, 
                                       tooltip_rect.width + 10, tooltip_rect.height + 4)
                pygame.draw.rect(screen, (60, 40, 40), tooltip_bg)
                pygame.draw.rect(screen, (200, 100, 100), tooltip_bg, 1)
                screen.blit(tooltip_surface, tooltip_rect)
        
        # Section 6: File Operations (bottom right)
        y_offset = 380
        section_title = font.render("File Operations", True, BUTTON_TEXT_COLOR)
        screen.blit(section_title, (right_margin - 200, y_offset))
        
        save_rect = pygame.Rect(right_margin - 200, y_offset + 30, 80, 30)
        load_rect = pygame.Rect(right_margin - 200, y_offset + 70, 80, 30)
        reset_rect = pygame.Rect(right_margin - 200, y_offset + 110, 80, 30)
        
        pygame.draw.rect(screen, BUTTON_COLOR, save_rect)
        pygame.draw.rect(screen, BUTTON_COLOR, load_rect)
        pygame.draw.rect(screen, BUTTON_COLOR, reset_rect)
        
        save_text = font.render("Save", True, BUTTON_TEXT_COLOR)
        load_text = font.render("Load", True, BUTTON_TEXT_COLOR)
        reset_text = font.render("Reset", True, BUTTON_TEXT_COLOR)
        
        screen.blit(save_text, (save_rect.centerx - save_text.get_width()//2, 
                               save_rect.centery - save_text.get_height()//2))
        screen.blit(load_text, (load_rect.centerx - load_text.get_width()//2, 
                               load_rect.centery - load_text.get_height()//2))
        screen.blit(reset_text, (reset_rect.centerx - reset_text.get_width()//2, 
                                reset_rect.centery - reset_text.get_height()//2))

        # Draw help text if an input is active
        if active_input is not None:
            if input_error:
                help_text = f"Error: {error_message} | Escape: Cancel"
                help_color = (255, 150, 150)
            else:
                help_text = "Enter: Apply | Escape: Cancel | Tab: Next | Shift+Tab: Previous"
                help_color = (150, 150, 150)
            
            help_surface = font.render(help_text, True, help_color)
            help_rect = help_surface.get_rect(centerx=WIN_WIDTH//2, y=WIN_HEIGHT - 60)
            screen.blit(help_surface, help_rect)
        
        # Draw close button (bottom center)
        button_hover = button_rect.collidepoint(mouse_pos)
        draw_button(screen, "Close", button_rect, button_hover)
    
    # Draw color picker popup if open
    if color_picker_open:
        popup_elements = draw_color_picker_popup()
    
    elif not settings_open:
        # Only show main content when settings are closed
        # Show mini screen when settings are closed (based on toggle)
        mini_visible = enable_mini_screen and not hide_minimap

        # Always draw trail if enabled and has enough points
        render_trail(screen, trail, trail_color, current_thickness, enable_trail, trail_fade)

        # Always draw cursor
        if trail:
            pygame.draw.circle(screen, cursor_color, trail[-1], 5)

        if not hide_ui:
            # Draw main grid if enabled
            if enable_main_grid:
                draw_grid(screen, WIN_WIDTH, WIN_HEIGHT, GRID_SPACING, GRID_COLOR)

            # Draw settings button (only when settings are closed)
            button_hover = button_rect.collidepoint(mouse_pos)
            draw_button(screen, "Settings", button_rect, button_hover)

    # Handle active area unlock timeout (reset clicks if too much time passes)
    if active_area_locked and active_area_unlock_clicks > 0:
        current_time = pygame.time.get_ticks()
        if current_time - active_area_unlock_timer > 3000:  # 3 seconds timeout
            active_area_unlock_clicks = 0
    
    # Always update and draw mini display if enabled
    if mini_visible and not hide_minimap:
        # Clear mini display
        small_screen.fill((10, 10, 10))

        # Draw mini grid if enabled
        if enable_mini_grid:
            draw_grid(small_screen, SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT, 10, GRID_COLOR)

        # Draw full tablet area outline (white)
        pygame.draw.rect(small_screen, (255, 255, 255), (0, 0, SMALL_WIN_WIDTH, SMALL_WIN_HEIGHT), 2)

        # Get current active area bounds
        active_bounds = get_active_area_bounds()

        # Calculate mini display coordinates for active area
        mini_active_x = (active_bounds['left'] / tablet_width) * SMALL_WIN_WIDTH
        mini_active_y = (active_bounds['top'] / tablet_height) * SMALL_WIN_HEIGHT
        mini_active_w = (active_bounds['width'] / tablet_width) * SMALL_WIN_WIDTH
        mini_active_h = (active_bounds['height'] / tablet_height) * SMALL_WIN_HEIGHT

        # Draw active area outline (customizable color and thickness)
        pygame.draw.rect(small_screen, active_area_color, 
                        (mini_active_x, mini_active_y, mini_active_w, mini_active_h), active_area_thickness)

        # Map cursor position to mini display
        mini_cursor_x = (tablet_mouse_x / tablet_width) * SMALL_WIN_WIDTH
        mini_cursor_y = (tablet_mouse_y / tablet_height) * SMALL_WIN_HEIGHT

        # Draw mini cursor
        pygame.draw.circle(small_screen, cursor_color, (int(mini_cursor_x), int(mini_cursor_y)), 3)

        # Draw to main screen
        screen.blit(small_screen, (WIN_WIDTH - SMALL_WIN_WIDTH - 10, WIN_HEIGHT - SMALL_WIN_HEIGHT - 10))

    if tooltip_active:
        draw_tooltip_overlay()
        pygame.display.update()
        clock.tick(60)
        # Do not continue; allow event processing below
    else:
        # Only show main content when settings are closed and not hiding UI
        if not settings_open and not hide_ui:
            # ... existing code ...
            mini_visible = enable_mini_screen and not hide_minimap
            pass
        # ... existing code ...
        if mini_visible and not hide_minimap:
            # ... existing code ...
            pass
    # ... existing code ...
    pygame.display.update()
    clock.tick(60)
    # ... existing code ...

    for event in pygame.event.get():
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
                else:
                    if button_rect.collidepoint(event.pos):
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

                    # Handle slider clicks
                    for i, slider in enumerate([trail_length_slider, smooth_factor_slider, trail_thickness_slider]):
                        if slider.collidepoint(event.pos):
                            slider_grabbed = ["trail", "smooth", "thickness"][i]
                            break
                    # Handle active area thickness slider (always available)
                    thickness_slider_rect = pygame.Rect(350, 80 + 105, 150, 15)
                    if thickness_slider_rect.collidepoint(event.pos):
                        slider_grabbed = "active_area_thickness"

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
                        for i in range(4):
                            if active_area_inputs[i].collidepoint(event.pos):
                                active_input = f"active_{i}"
                                input_text = str(active_area_values[i])
                                input_clicked = True
                                break
                    # If no input box was clicked, clear all inputs
                    if not input_clicked:
                        deactivate_all_inputs()
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:  # Left click release
                slider_grabbed = False
                # Stop color picker dragging
                color_picker_dragging = False
                color_picker_drag_type = None
        
        elif event.type == pygame.MOUSEMOTION:
            if slider_grabbed:
                if slider_grabbed == "trail":
                    rel_x = event.pos[0] - trail_length_slider.x
                    current_trail_length = int(min_trail_length + 
                        (max_trail_length_limit - min_trail_length) * 
                        (rel_x / SLIDER_WIDTH))
                    current_trail_length = max(min_trail_length, 
                        min(max_trail_length_limit, current_trail_length))
                elif slider_grabbed == "smooth":
                    rel_x = event.pos[0] - smooth_factor_slider.x
                    current_smooth = min_smooth + (max_smooth - min_smooth) * (rel_x / SLIDER_WIDTH)
                    current_smooth = max(min_smooth, min(max_smooth, current_smooth))
                elif slider_grabbed == "thickness":
                    rel_x = event.pos[0] - trail_thickness_slider.x
                    current_thickness = int(min_thickness + 
                        (max_thickness - min_thickness) * (rel_x / SLIDER_WIDTH))
                    current_thickness = max(min_thickness, min(max_thickness, current_thickness))
                elif slider_grabbed == "active_area_thickness":
                    thickness_slider_rect = pygame.Rect(350, 80 + 105, 150, 15)
                    rel_x = event.pos[0] - thickness_slider_rect.x
                    active_area_thickness = int(1 + (rel_x / 150) * 4)  # 1-5 range
                    active_area_thickness = max(1, min(5, active_area_thickness))
            
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
                        angle = np.degrees(np.arctan2(dy, dx)) % 360
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
                if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                    # Apply the value
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
                                    active_area_values[index] = 1  # Default minimum value
                                    active_width = active_area_values[2]
                                    active_height = active_area_values[3]
                            else:
                                value = int(input_text)

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
                                    if value < 1:
                                        input_error = True
                                        error_message = "Active area values must be at least 1"
                                    else:
                                        active_area_values[index] = value
                                        active_width = active_area_values[2]
                                        active_height = active_area_values[3]

                        except ValueError:
                            input_error = True
                            error_message = "Please enter a valid number"
                    
                    # Only clear if no error
                    if not input_error:
                        active_input = None
                        input_text = ""

                elif event.key == pygame.K_ESCAPE:
                    # Cancel editing - restore original value
                    active_input = None
                    input_text = ""
                    input_error = False
                    error_message = ""

                elif event.key == pygame.K_TAB:
                    # Tab navigation between input boxes
                    if event.mod & pygame.KMOD_SHIFT:
                        # Shift+Tab - go backwards
                        if active_input.startswith("cursor"):
                            if active_input == "cursor_0":
                                active_input = "active_3"  # Go to last active area input
                            else:
                                index = int(active_input.split("_")[1])
                                active_input = f"cursor_{index-1}"
                        elif active_input.startswith("trail"):
                            if active_input == "trail_0":
                                active_input = "cursor_2"  # Go to last cursor input
                            else:
                                index = int(active_input.split("_")[1])
                                active_input = f"trail_{index-1}"
                        elif active_input.startswith("active"):
                            if active_input == "active_0":
                                active_input = "trail_2"  # Go to last trail input
                            else:
                                index = int(active_input.split("_")[1])
                                active_input = f"active_{index-1}"
                    else:
                        # Tab - go forwards
                        if active_input.startswith("cursor"):
                            if active_input == "cursor_2":
                                active_input = "trail_0"  # Go to first trail input
                            else:
                                index = int(active_input.split("_")[1])
                                active_input = f"cursor_{index+1}"
                        elif active_input.startswith("trail"):
                            if active_input == "trail_2":
                                active_input = "active_0"  # Go to first active area input
                            else:
                                index = int(active_input.split("_")[1])
                                active_input = f"trail_{index+1}"
                        elif active_input.startswith("active"):
                            if active_input == "active_3":
                                active_input = "cursor_0"  # Go to first cursor input
                            else:
                                index = int(active_input.split("_")[1])
                                active_input = f"active_{index+1}"
                    
                    # Clear error state when switching inputs
                    input_error = False
                    error_message = ""
                    
                    # Update input text for the new active input
                    if active_input.startswith("cursor") and not active_input.endswith("_hex"):
                        index = int(active_input.split("_")[1])
                        input_text = str(cursor_rgb_values[index])
                    elif active_input.startswith("trail") and not active_input.endswith("_hex"):
                        index = int(active_input.split("_")[1])
                        input_text = str(trail_rgb_values[index])
                    elif active_input.startswith("active"):
                        index = int(active_input.split("_")[1])
                        input_text = str(active_area_values[index])
                    elif active_input.endswith("_hex"):
                        if active_input == "cursor_hex":
                            input_text = rgb_to_hex(*cursor_rgb_values)
                        elif active_input == "trail_hex":
                            input_text = rgb_to_hex(*trail_rgb_values)
                        elif active_input == "rectangle_hex":
                            input_text = rgb_to_hex(*active_area_rgb_values)
                        elif active_input == "background_hex":
                            input_text = rgb_to_hex(*background_rgb_values)

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
                    # Option 2: Hide UI (but keep minimap)
                    if hide_ui and not hide_minimap:
                        # Already in option 2 mode, revert to normal
                        hide_ui = False
                        hide_minimap = False
                    else:
                        # Switch to option 2 mode
                        hide_ui = True
                        hide_minimap = False
                    tooltip_active = False
                elif event.key == pygame.K_3:
                    # Option 3: Hide UI + minimap
                    if hide_ui and hide_minimap:
                        # Already in option 3 mode, revert to normal
                        hide_ui = False
                        hide_minimap = False
                    else:
                        # Switch to option 3 mode
                        hide_ui = True
                        hide_minimap = True
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





pygame.quit()