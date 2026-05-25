import time
import csv
import mss
import cv2
import numpy as np
import pytesseract
import sys
import os
import json
import tkinter as tk
from tkinter import colorchooser, messagebox
import threading
import queue

# ==========================================
# CONFIGURATION MANAGEMENT
# ==========================================

CONFIG_PATH = 'config.json'

DEFAULT_CONFIG = {
    'overlay': {
        'enabled': True,
        'x': 1800,
        'y': 750,
        'font_size': 18,
        'text_color': "#FFFF00",
        'bg_color': "#1a1a1e",
        'bg_opacity': 0.7,
        'use_transparent_bg': False
    },
    'monitor': {
        'top': 715,
        'left': 1909,
        'width': 70,
        'height': 29
    },
    'tesseract_cmd': r'C:\Program Files\Tesseract-OCR\tesseract.exe'
}

CONFIG = {}

def load_config():
    global CONFIG
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
            # Merge defaults for any missing keys
            for section in DEFAULT_CONFIG:
                if section not in CONFIG:
                    CONFIG[section] = DEFAULT_CONFIG[section]
                elif isinstance(DEFAULT_CONFIG[section], dict):
                    for key in DEFAULT_CONFIG[section]:
                        if key not in CONFIG[section]:
                            CONFIG[section][key] = DEFAULT_CONFIG[section][key]
        except Exception as e:
            print(f"Error loading config.json: {e}. Using defaults.")
            CONFIG = DEFAULT_CONFIG.copy()
    else:
        CONFIG = DEFAULT_CONFIG.copy()
        save_config()

def save_config():
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, indent=4)
    except Exception as e:
        print(f"Error saving config.json: {e}")

# Load configuration at startup
load_config()

# Set initial tesseract path
pytesseract.pytesseract.tesseract_cmd = CONFIG['tesseract_cmd']

# ==========================================
# SIGNATURES AND IMAGE PREPROCESSING
# ==========================================

def load_signatures(filepath):
    """
    Reads the signatures.csv and returns a dictionary mapping
    numeric values (as string) to a descriptive string (Name, Tier, Multiplier)
    """
    lookup = {}
    try:
        with open(filepath, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader) # Skip header line
            
            for row in reader:
                if not row or not row[0]:
                    continue
                    
                name = row[0]
                tier = row[1]
                
                # Values start from index 2
                for idx, val in enumerate(row[2:]):
                    if val.strip():
                        try:
                            # Clean the value (e.g., '10110.0' -> '10110')
                            num_str = str(int(float(val.strip())))
                            multiplier = f"{idx + 1}x"
                            lookup[num_str] = f"{name} ({tier}) - {multiplier}"
                        except ValueError:
                            pass
    except FileNotFoundError:
        print(f"Error: Could not find '{filepath}'. Make sure it's in the same directory.")
        sys.exit(1)
        
    return lookup

def preprocess_image(img):
    """
    Preprocess the image to improve OCR accuracy.
    """
    # Convert from BGRA to Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    
    # Scale up the image significantly (3x or 4x often works better than 2x for small text)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # Apply automatic thresholding (also consider cv2.THRESH_BINARY_INV for inverted colours)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # --- NEW: Morphological cleaning ---
    # Create a small 2x2 kernel
    kernel = np.ones((2, 2), np.uint8)
    
    # Use MORPH_OPEN to remove isolated noise spots and crisp up digit loops
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    
    return thresh

# ==========================================
# BACKGROUND SCRAPER WORKER THREAD
# ==========================================

def scraper_worker(signatures_lookup, gui_queue):
    print("\nStarting screen capture thread...")
    last_match_time = None
    
    with mss.MSS() as sct:
        try:
            while True:
                # Capture current CONFIG coordinates
                monitor = {
                    'top': CONFIG['monitor']['top'],
                    'left': CONFIG['monitor']['left'],
                    'width': CONFIG['monitor']['width'],
                    'height': CONFIG['monitor']['height']
                }
                
                # Make sure coordinates are valid to prevent mss crash
                if monitor['width'] > 0 and monitor['height'] > 0:
                    sct_img = sct.grab(monitor)
                    img = np.array(sct_img)
                    processed_img = preprocess_image(img)
                    
                    # Ensure Tesseract path is set from config
                    pytesseract.pytesseract.tesseract_cmd = CONFIG['tesseract_cmd']
                    
                    # --psm 7 (Treat the image as a single text line) or --psm 8 (Treat the image as a single word).
                    custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789'
                    text = pytesseract.image_to_string(processed_img, config=custom_config).strip()
                    
                    if text and text in signatures_lookup:
                        match_str = signatures_lookup[text]
                        print(f"[MATCH] Found {text} -> {match_str}")
                        gui_queue.put({"type": "ocr_feed", "text": text, "is_match": True, "match_str": match_str})
                        gui_queue.put({"type": "overlay_match", "match_str": match_str})
                        last_match_time = time.time()
                    else:
                        if text:
                            print(f"[INFO] OCR read '{text}', but it is not in signatures.csv.")
                            gui_queue.put({"type": "ocr_feed", "text": text, "is_match": False, "match_str": ""})
                        else:
                            gui_queue.put({"type": "ocr_feed", "text": "---", "is_match": False, "match_str": ""})
                        
                        # Clear overlay if 2 seconds have passed since last match
                        if last_match_time is not None and (time.time() - last_match_time > 2.0):
                            gui_queue.put({"type": "overlay_clear"})
                            last_match_time = None
                
                time.sleep(0.5)
        except Exception as e:
            print(f"\nScraper error: {e}")
            gui_queue.put({"type": "error", "message": str(e)})

# ==========================================
# GUI DASHBOARD AND OVERLAY
# ==========================================

# Modern Dark Theme Colors
BG_MAIN = "#121214"
BG_CARD = "#1c1c22"
BG_INPUT = "#2b2b36"
FG_TEXT = "#e1e1e6"
FG_MUTED = "#8f8f9d"
COLOR_ACCENT = "#6c5ce7"
COLOR_ACCENT_HOVER = "#8073e6"
COLOR_SUCCESS = "#00b894"
COLOR_DANGER = "#ff7675"

class SiggyApp:
    def __init__(self, root, signatures_lookup, match_queue):
        self.root = root
        self.signatures_lookup = signatures_lookup
        self.match_queue = match_queue
        
        # Window configuration
        self.root.title("Siggy Controller")
        self.root.geometry("440x710")
        self.root.configure(bg=BG_MAIN)
        self.root.resizable(False, False)
        
        # State variables
        self.unlocked = False
        self.current_match = ""
        self.finder_clicks = []
        
        # Build UI Elements
        self.create_dashboard_ui()
        
        # Initialize overlay
        self.overlay_window = None
        if CONFIG['overlay']['enabled']:
            self.create_overlay_window()
            
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Start queue processing loop
        self.check_queue()

    def create_dashboard_ui(self):
        # 1. Header Frame
        header = tk.Frame(self.root, bg=BG_MAIN)
        header.pack(fill="x", padx=20, pady=(15, 5))
        
        self.status_dot = tk.Canvas(header, width=12, height=12, bg=BG_MAIN, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 10))
        self.status_dot_id = self.status_dot.create_oval(2, 2, 10, 10, fill=COLOR_SUCCESS, outline="")
        
        lbl_title = tk.Label(header, text="SIGGY CONTROLLER", bg=BG_MAIN, fg=FG_TEXT, font=("Segoe UI", 12, "bold"))
        lbl_title.pack(side="left")
        
        self.lbl_status_desc = tk.Label(self.root, text="Scraper actively scanning screen region", bg=BG_MAIN, fg=FG_MUTED, font=("Segoe UI", 9))
        self.lbl_status_desc.pack(anchor="w", padx=42, pady=(0, 10))

        # Divider
        div = tk.Frame(self.root, height=1, bg=BG_INPUT)
        div.pack(fill="x", padx=20, pady=5)

        # 2. Live OCR Feed Card
        card_ocr = tk.Frame(self.root, bg=BG_CARD, bd=0)
        card_ocr.pack(fill="x", padx=20, pady=8)
        
        tk.Label(card_ocr, text="LIVE OCR SCANNER", bg=BG_CARD, fg=COLOR_ACCENT, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        
        feed_frame = tk.Frame(card_ocr, bg=BG_CARD)
        feed_frame.pack(fill="x", padx=12, pady=(0, 8))
        
        tk.Label(feed_frame, text="Read:", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 10)).pack(side="left")
        self.lbl_ocr_read = tk.Label(feed_frame, text="---", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 12, "bold"))
        self.lbl_ocr_read.pack(side="left", padx=5)
        
        self.lbl_ocr_match = tk.Label(feed_frame, text="No active database match", bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 10, "italic"))
        self.lbl_ocr_match.pack(side="right", padx=(10, 0))

        # 3. Scanner Coordinates Card
        card_coords = tk.Frame(self.root, bg=BG_CARD, bd=0)
        card_coords.pack(fill="x", padx=20, pady=8)
        
        tk.Label(card_coords, text="CAPTURE AREA COORDINATES", bg=BG_CARD, fg=COLOR_ACCENT, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        
        coords_grid = tk.Frame(card_coords, bg=BG_CARD)
        coords_grid.pack(fill="x", padx=12, pady=5)
        
        # Row 1
        tk.Label(coords_grid, text="Left:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=4)
        self.ent_left = tk.Entry(coords_grid, width=8, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, bd=0, highlightthickness=1, highlightbackground=BG_INPUT, highlightcolor=COLOR_ACCENT, font=("Segoe UI", 9))
        self.ent_left.grid(row=0, column=1, padx=(5, 15), pady=4)
        self.ent_left.insert(0, str(CONFIG['monitor']['left']))
        
        tk.Label(coords_grid, text="Top:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", pady=4)
        self.ent_top = tk.Entry(coords_grid, width=8, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, bd=0, highlightthickness=1, highlightbackground=BG_INPUT, highlightcolor=COLOR_ACCENT, font=("Segoe UI", 9))
        self.ent_top.grid(row=0, column=3, padx=5, pady=4)
        self.ent_top.insert(0, str(CONFIG['monitor']['top']))
        
        # Row 2
        tk.Label(coords_grid, text="Width:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=4)
        self.ent_width = tk.Entry(coords_grid, width=8, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, bd=0, highlightthickness=1, highlightbackground=BG_INPUT, highlightcolor=COLOR_ACCENT, font=("Segoe UI", 9))
        self.ent_width.grid(row=1, column=1, padx=(5, 15), pady=4)
        self.ent_width.insert(0, str(CONFIG['monitor']['width']))
        
        tk.Label(coords_grid, text="Height:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).grid(row=1, column=2, sticky="w", pady=4)
        self.ent_height = tk.Entry(coords_grid, width=8, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, bd=0, highlightthickness=1, highlightbackground=BG_INPUT, highlightcolor=COLOR_ACCENT, font=("Segoe UI", 9))
        self.ent_height.grid(row=1, column=3, padx=5, pady=4)
        self.ent_height.insert(0, str(CONFIG['monitor']['height']))
        
        # Action Buttons
        coords_btn_frame = tk.Frame(card_coords, bg=BG_CARD)
        coords_btn_frame.pack(fill="x", padx=12, pady=(4, 10))
        
        self.btn_save_coords = tk.Button(
            coords_btn_frame, text="SAVE COORDINATES", bg=BG_INPUT, fg=FG_TEXT, 
            activebackground=COLOR_ACCENT, activeforeground=FG_TEXT, bd=0, relief="flat", 
            font=("Segoe UI", 9, "bold"), height=1, command=self.save_coordinates
        )
        self.btn_save_coords.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_finder = tk.Button(
            coords_btn_frame, text="SCAN REGION FINDER", bg=COLOR_ACCENT, fg=FG_TEXT, 
            activebackground=COLOR_ACCENT_HOVER, activeforeground=FG_TEXT, bd=0, relief="flat", 
            font=("Segoe UI", 9, "bold"), height=1, command=self.start_coordinate_finder
        )
        self.btn_finder.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # 4. Overlay Appearance Controls Card
        card_overlay = tk.Frame(self.root, bg=BG_CARD, bd=0)
        card_overlay.pack(fill="x", padx=20, pady=8)
        
        tk.Label(card_overlay, text="OVERLAY APPEARANCE", bg=BG_CARD, fg=COLOR_ACCENT, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        
        # Checkboxes
        self.var_overlay_enabled = tk.BooleanVar(value=CONFIG['overlay']['enabled'])
        self.chk_overlay_enabled = tk.Checkbutton(
            card_overlay, text="Enable Overlay Window", variable=self.var_overlay_enabled, 
            command=self.toggle_overlay, bg=BG_CARD, fg=FG_TEXT, activebackground=BG_CARD, 
            activeforeground=FG_TEXT, selectcolor=BG_INPUT, font=("Segoe UI", 9)
        )
        self.chk_overlay_enabled.pack(anchor="w", padx=12, pady=2)

        self.var_trans_bg = tk.BooleanVar(value=CONFIG['overlay']['use_transparent_bg'])
        self.chk_trans_bg = tk.Checkbutton(
            card_overlay, text="Transparent Background (Text Only)", variable=self.var_trans_bg, 
            command=self.toggle_transparency_mode, bg=BG_CARD, fg=FG_TEXT, activebackground=BG_CARD, 
            activeforeground=FG_TEXT, selectcolor=BG_INPUT, font=("Segoe UI", 9)
        )
        self.chk_trans_bg.pack(anchor="w", padx=12, pady=2)

        # Color controls frame
        color_frame = tk.Frame(card_overlay, bg=BG_CARD)
        color_frame.pack(fill="x", padx=12, pady=4)
        
        tk.Label(color_frame, text="Text:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=4)
        self.btn_text_color = tk.Button(color_frame, width=4, height=1, bd=1, relief="solid", command=self.choose_text_color)
        self.btn_text_color.grid(row=0, column=1, padx=(6, 6), pady=4)
        self.lbl_text_color_hex = tk.Label(color_frame, text=CONFIG['overlay']['text_color'], bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9))
        self.lbl_text_color_hex.grid(row=0, column=2, sticky="w", pady=4)
        
        tk.Label(color_frame, text="Background:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).grid(row=0, column=3, sticky="w", padx=(25, 0), pady=4)
        self.btn_bg_color = tk.Button(color_frame, width=4, height=1, bd=1, relief="solid", command=self.choose_bg_color)
        self.btn_bg_color.grid(row=0, column=4, padx=(6, 6), pady=4)
        self.lbl_bg_color_hex = tk.Label(color_frame, text=CONFIG['overlay']['bg_color'], bg=BG_CARD, fg=FG_MUTED, font=("Segoe UI", 9))
        self.lbl_bg_color_hex.grid(row=0, column=5, sticky="w", pady=4)
        
        # Font size scale
        font_frame = tk.Frame(card_overlay, bg=BG_CARD)
        font_frame.pack(fill="x", padx=12, pady=4)
        tk.Label(font_frame, text="Font Size:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).pack(side="left")
        self.slider_font = tk.Scale(
            font_frame, from_=10, to=48, orient="horizontal", bg=BG_CARD, fg=FG_TEXT, 
            highlightthickness=0, troughcolor=BG_INPUT, activebackground=COLOR_ACCENT,
            command=self.on_font_slider_change, showvalue=True
        )
        self.slider_font.set(CONFIG['overlay']['font_size'])
        self.slider_font.pack(side="right", fill="x", expand=True, padx=(10, 0))
        
        # Opacity scale
        self.opacity_frame = tk.Frame(card_overlay, bg=BG_CARD)
        self.opacity_frame.pack(fill="x", padx=12, pady=(4, 10))
        tk.Label(self.opacity_frame, text="Opacity:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).pack(side="left")
        self.slider_opacity = tk.Scale(
            self.opacity_frame, from_=0.1, to=1.0, resolution=0.05, orient="horizontal", bg=BG_CARD, fg=FG_TEXT, 
            highlightthickness=0, troughcolor=BG_INPUT, activebackground=COLOR_ACCENT,
            command=self.on_opacity_slider_change, showvalue=True
        )
        self.slider_opacity.set(CONFIG['overlay']['bg_opacity'])
        self.slider_opacity.pack(side="right", fill="x", expand=True, padx=(14, 0))

        # 5. Position & Move Card
        card_move = tk.Frame(self.root, bg=BG_CARD, bd=0)
        card_move.pack(fill="x", padx=20, pady=8)
        
        tk.Label(card_move, text="OVERLAY POSITION", bg=BG_CARD, fg=COLOR_ACCENT, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        
        pos_info = tk.Frame(card_move, bg=BG_CARD)
        pos_info.pack(fill="x", padx=12, pady=4)
        
        tk.Label(pos_info, text="Coordinates:", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9)).pack(side="left")
        self.lbl_pos_val = tk.Label(pos_info, text=f"X: {CONFIG['overlay']['x']}, Y: {CONFIG['overlay']['y']}", bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 9, "bold"))
        self.lbl_pos_val.pack(side="right")
        
        self.btn_drag = tk.Button(
            card_move, text="UNLOCK & MOVE OVERLAY", bg=COLOR_ACCENT, fg=FG_TEXT, 
            activebackground=COLOR_ACCENT_HOVER, activeforeground=FG_TEXT, bd=0, relief="flat", 
            font=("Segoe UI", 9, "bold"), height=1, command=self.toggle_drag_mode
        )
        self.btn_drag.pack(fill="x", padx=12, pady=(4, 10))

        # Initial GUI state configuration
        self.update_color_button_views()
        self.update_control_states()

    # Dynamic states and choices
    def update_color_button_views(self):
        self.btn_text_color.config(bg=CONFIG['overlay']['text_color'], activebackground=CONFIG['overlay']['text_color'])
        self.lbl_text_color_hex.config(text=CONFIG['overlay']['text_color'])
        
        self.btn_bg_color.config(bg=CONFIG['overlay']['bg_color'], activebackground=CONFIG['overlay']['bg_color'])
        self.lbl_bg_color_hex.config(text=CONFIG['overlay']['bg_color'])

    def update_control_states(self):
        use_trans = self.var_trans_bg.get()
        if use_trans:
            self.btn_bg_color.config(state="disabled")
            self.slider_opacity.config(state="disabled", fg=FG_MUTED)
        else:
            self.btn_bg_color.config(state="normal")
            self.slider_opacity.config(state="normal", fg=FG_TEXT)

    def choose_text_color(self):
        color = colorchooser.askcolor(initialcolor=CONFIG['overlay']['text_color'], title="Choose Text Color")
        if color[1]:
            CONFIG['overlay']['text_color'] = color[1]
            save_config()
            self.update_color_button_views()
            self.update_overlay_style()
            
    def choose_bg_color(self):
        color = colorchooser.askcolor(initialcolor=CONFIG['overlay']['bg_color'], title="Choose Background Color")
        if color[1]:
            CONFIG['overlay']['bg_color'] = color[1]
            save_config()
            self.update_color_button_views()
            self.update_overlay_style()

    def on_font_slider_change(self, val):
        CONFIG['overlay']['font_size'] = int(val)
        save_config()
        self.update_overlay_style()
        
    def on_opacity_slider_change(self, val):
        CONFIG['overlay']['bg_opacity'] = float(val)
        save_config()
        self.update_overlay_style()

    def toggle_overlay(self):
        enabled = self.var_overlay_enabled.get()
        CONFIG['overlay']['enabled'] = enabled
        save_config()
        
        if enabled:
            self.create_overlay_window()
        else:
            if self.overlay_window:
                self.overlay_window.destroy()
                self.overlay_window = None

    def toggle_transparency_mode(self):
        use_trans = self.var_trans_bg.get()
        CONFIG['overlay']['use_transparent_bg'] = use_trans
        save_config()
        
        self.update_control_states()
        self.update_overlay_style()

    # Overlay creation and styling
    def create_overlay_window(self):
        if self.overlay_window:
            self.overlay_window.destroy()
            
        self.overlay_window = tk.Toplevel(self.root)
        self.overlay_window.title("Siggy Overlay")
        self.overlay_window.overrideredirect(True)
        self.overlay_window.wm_attributes("-topmost", True)
        
        # Position
        x = CONFIG['overlay']['x']
        y = CONFIG['overlay']['y']
        self.overlay_window.geometry(f"+{x}+{y}")
        
        # Overlay label
        self.overlay_label = tk.Label(
            self.overlay_window, 
            text=self.current_match if self.current_match else "",
            font=("Arial", CONFIG['overlay']['font_size'], "bold")
        )
        self.overlay_label.pack(padx=12, pady=6)
        
        self.update_overlay_style()

    def update_overlay_style(self):
        if not self.overlay_window:
            return
            
        overlay_cfg = CONFIG['overlay']
        
        if self.unlocked:
            # Edit drag mode
            self.overlay_window.wm_attributes("-disabled", False)
            self.overlay_window.wm_attributes("-transparentcolor", "")
            
            edit_bg = "#34495e"
            edit_fg = "#ffffff"
            self.overlay_window.configure(bg=edit_bg)
            self.overlay_label.configure(
                bg=edit_bg, 
                fg=edit_fg, 
                text="[DRAG ME] - Siggy Overlay",
                font=("Arial", overlay_cfg['font_size'], "bold"),
                cursor="fleur"
            )
            self.overlay_window.wm_attributes("-alpha", 0.85)
            self.overlay_window.deiconify() # Force visible in edit mode
            
            # Bind drag behaviors
            self.overlay_window.bind("<Button-1>", self.start_drag)
            self.overlay_window.bind("<B1-Motion>", self.drag)
            self.overlay_window.bind("<ButtonRelease-1>", self.stop_drag)
            self.overlay_label.bind("<Button-1>", self.start_drag)
            self.overlay_label.bind("<B1-Motion>", self.drag)
            self.overlay_label.bind("<ButtonRelease-1>", self.stop_drag)
        else:
            # Click-through active scanning mode
            self.overlay_window.wm_attributes("-disabled", True)
            
            # Unbind drag behaviors
            self.overlay_window.unbind("<Button-1>")
            self.overlay_window.unbind("<B1-Motion>")
            self.overlay_window.unbind("<ButtonRelease-1>")
            self.overlay_label.unbind("<Button-1>")
            self.overlay_label.unbind("<B1-Motion>")
            self.overlay_label.unbind("<ButtonRelease-1>")
            self.overlay_label.configure(cursor="")
            
            self.overlay_label.configure(
                text=self.current_match,
                font=("Arial", overlay_cfg['font_size'], "bold"),
                fg=overlay_cfg['text_color']
            )
            
            if overlay_cfg['use_transparent_bg']:
                transparent_key = "black" if overlay_cfg['text_color'].lower() != "black" else "white"
                self.overlay_window.wm_attributes("-transparentcolor", transparent_key)
                self.overlay_window.configure(bg=transparent_key)
                self.overlay_label.configure(bg=transparent_key)
                self.overlay_window.wm_attributes("-alpha", 1.0)
            else:
                bg_col = overlay_cfg['bg_color']
                self.overlay_window.wm_attributes("-transparentcolor", "")
                self.overlay_window.configure(bg=bg_col)
                self.overlay_label.configure(bg=bg_col)
                self.overlay_window.wm_attributes("-alpha", overlay_cfg['bg_opacity'])
                
            # Show if there is a match, hide if there isn't
            if self.current_match:
                self.overlay_window.deiconify()
            else:
                self.overlay_window.withdraw()

    # Drag operations
    def start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def drag(self, event):
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        current_x = self.overlay_window.winfo_x()
        current_y = self.overlay_window.winfo_y()
        new_x = current_x + dx
        new_y = current_y + dy
        self.overlay_window.geometry(f"+{new_x}+{new_y}")
        self.lbl_pos_val.config(text=f"X: {new_x}, Y: {new_y}")

    def stop_drag(self, event):
        CONFIG['overlay']['x'] = self.overlay_window.winfo_x()
        CONFIG['overlay']['y'] = self.overlay_window.winfo_y()
        save_config()

    def toggle_drag_mode(self):
        if not CONFIG['overlay']['enabled']:
            self.var_overlay_enabled.set(True)
            self.toggle_overlay()
            
        self.unlocked = not self.unlocked
        if self.unlocked:
            self.btn_drag.config(text="LOCK POSITION & CLICK-THROUGH", bg=COLOR_DANGER, activebackground="#ff5252")
            self.update_overlay_style()
        else:
            self.btn_drag.config(text="UNLOCK & MOVE OVERLAY", bg=COLOR_ACCENT, activebackground=COLOR_ACCENT_HOVER)
            self.update_overlay_style()

    # Manual Coordinate Save
    def save_coordinates(self):
        try:
            left = int(self.ent_left.get())
            top = int(self.ent_top.get())
            width = int(self.ent_width.get())
            height = int(self.ent_height.get())
            
            CONFIG['monitor']['left'] = left
            CONFIG['monitor']['top'] = top
            CONFIG['monitor']['width'] = width
            CONFIG['monitor']['height'] = height
            
            save_config()
            self.btn_save_coords.config(text="SAVED!", bg=COLOR_SUCCESS)
            self.root.after(1500, lambda: self.btn_save_coords.config(text="SAVE COORDINATES", bg=BG_INPUT))
        except ValueError:
            messagebox.showerror("Error", "All scan coordinates must be integers!")

    # Threaded coordinate helper
    def start_coordinate_finder(self):
        self.btn_finder.config(state="disabled", text="CLICK TOP-LEFT...", bg=COLOR_DANGER)
        self.finder_clicks = []
        
        self.listener_thread = threading.Thread(target=self.run_mouse_listener, daemon=True)
        self.listener_thread.start()
        
    def run_mouse_listener(self):
        from pynput import mouse
        
        def on_click(x, y, button, pressed):
            if pressed:
                self.finder_clicks.append((int(x), int(y)))
                if len(self.finder_clicks) == 1:
                    self.root.after(0, lambda: self.btn_finder.config(text="CLICK BOTTOM-RIGHT..."))
                elif len(self.finder_clicks) == 2:
                    x1, y1 = self.finder_clicks[0]
                    x2, y2 = self.finder_clicks[1]
                    
                    top = min(y1, y2)
                    left = min(x1, x2)
                    width = abs(x2 - x1)
                    height = abs(y2 - y1)
                    
                    self.root.after(0, lambda: self.finish_coordinate_finder(top, left, width, height))
                    return False
        
        with mouse.Listener(on_click=on_click) as listener:
            listener.join()
            
    def finish_coordinate_finder(self, top, left, width, height):
        self.ent_top.delete(0, tk.END)
        self.ent_top.insert(0, str(top))
        self.ent_left.delete(0, tk.END)
        self.ent_left.insert(0, str(left))
        self.ent_width.delete(0, tk.END)
        self.ent_width.insert(0, str(width))
        self.ent_height.delete(0, tk.END)
        self.ent_height.insert(0, str(height))
        
        CONFIG['monitor']['top'] = top
        CONFIG['monitor']['left'] = left
        CONFIG['monitor']['width'] = width
        CONFIG['monitor']['height'] = height
        save_config()
        
        self.btn_finder.config(state="normal", text="SCAN REGION FINDER", bg=COLOR_ACCENT)
        messagebox.showinfo("Success", f"Capture coordinates set successfully:\nLeft: {left}, Top: {top}, Width: {width}, Height: {height}")

    # Set graphical application status
    def set_status(self, is_running, error_msg=None):
        if is_running:
            self.status_dot.itemconfig(self.status_dot_id, fill=COLOR_SUCCESS)
            self.lbl_status_desc.config(text="Scraper actively scanning screen region", fg=FG_MUTED)
        else:
            self.status_dot.itemconfig(self.status_dot_id, fill=COLOR_DANGER)
            if error_msg:
                self.lbl_status_desc.config(text=f"ERROR: {error_msg}", fg=COLOR_DANGER)
            else:
                self.lbl_status_desc.config(text="Scraper is idle or stopped", fg=FG_MUTED)

    # Queue checker loop
    def check_queue(self):
        try:
            while True:
                msg = self.match_queue.get_nowait()
                msg_type = msg.get("type")
                
                if msg_type == "ocr_feed":
                    text = msg.get("text", "---")
                    is_match = msg.get("is_match", False)
                    match_str = msg.get("match_str", "")
                    
                    self.lbl_ocr_read.config(text=f"'{text}'")
                    if is_match:
                        self.lbl_ocr_match.config(text=match_str, fg=COLOR_SUCCESS)
                    else:
                        self.lbl_ocr_match.config(text="No active database match", fg=FG_MUTED)
                        
                elif msg_type == "overlay_match":
                    match_str = msg.get("match_str", "")
                    self.current_match = match_str
                    if CONFIG['overlay']['enabled'] and self.overlay_window and not self.unlocked:
                        self.overlay_label.config(text=match_str)
                        self.overlay_window.deiconify()
                        
                elif msg_type == "overlay_clear":
                    self.current_match = ""
                    if CONFIG['overlay']['enabled'] and self.overlay_window and not self.unlocked:
                        self.overlay_label.config(text="")
                        self.overlay_window.withdraw()
                        
                elif msg_type == "error":
                    err_msg = msg.get("message", "Unknown error")
                    self.set_status(False, err_msg)
                    
        except queue.Empty:
            pass
            
        self.root.after(100, self.check_queue)

    def on_close(self):
        # Stop background thread by terminating parent application
        self.root.destroy()
        sys.exit(0)

# ==========================================
# MAIN EXECUTION ENTRY
# ==========================================

def main():
    print("Loading signatures from signatures.csv...")
    signatures_lookup = load_signatures('signatures.csv')
    print(f"Loaded {len(signatures_lookup)} values into lookup dictionary.")
    
    gui_queue = queue.Queue()
    
    # Start scraper in a background thread
    t = threading.Thread(target=scraper_worker, args=(signatures_lookup, gui_queue), daemon=True)
    t.start()
    
    # Start Tkinter main loop
    root = tk.Tk()
    app = SiggyApp(root, signatures_lookup, gui_queue)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
