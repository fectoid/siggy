import time
import csv
import mss
import cv2
import numpy as np
import pytesseract
import sys
import tkinter as tk
import threading
import queue

# ==========================================
# CONFIGURATION
# ==========================================

# Overlay Settings
OVERLAY = {
    'enabled': True,
    'x': 1900,      # X position of the overlay on screen
    'y': 800,       # Y position of the overlay on screen
    'font_size': 24,
    'color': "yellow"
}

# Replace this with the output from find_coords.py
MONITOR = {
    'top': 715,
    'left': 1904,
    'width': 118,
    'height': 34
}

# Path to your tesseract executable. 
# Typical installation path on Windows:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Tesseract needs to be installed: https://github.com/UB-Mannheim/tesseract/wiki
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

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
            header = next(reader) # Skip header line
            
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
    # Convert from BGRA (mss default) to Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    
    # Scale up the image to improve OCR of small text
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    # Apply thresholding
    # Depending on whether the text is white on dark background or vice versa,
    # you might need THRESH_BINARY or THRESH_BINARY_INV.
    # We use Otsu's thresholding for automatic threshold calculation.
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    return thresh

def scraper_worker(signatures_lookup, match_queue):
    print("\nStarting screen capture (polling twice a second)...")
    print("Make sure you've updated the MONITOR coordinates and Tesseract path in the script!")
    print("Press Ctrl+C in terminal to stop.\n")
    
    last_match_time = None
    
    with mss.MSS() as sct:
        try:
            while True:
                # Capture the screen region
                sct_img = sct.grab(MONITOR)
                
                # Convert to numpy array
                img = np.array(sct_img)
                
                # Preprocess for OCR
                processed_img = preprocess_image(img)
                
                # Run OCR
                custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
                text = pytesseract.image_to_string(processed_img, config=custom_config).strip()
                
                if text and text in signatures_lookup:
                    match_str = signatures_lookup[text]
                    print(f"[MATCH] Found {text} -> {match_str}")
                    match_queue.put(match_str)
                    last_match_time = time.time()
                else:
                    if text:
                        print(f"[INFO] OCR read '{text}', but it is not in signatures.csv.")
                    
                    # If we had a previous match and 2 seconds have passed, clear the overlay
                    if last_match_time is not None and (time.time() - last_match_time > 2.0):
                        match_queue.put("") 
                        last_match_time = None # Reset so we don't keep clearing

                
                time.sleep(0.5)
                
        except Exception as e:
            print(f"\nStopped: {e}")

def check_queue(root, label, match_queue):
    try:
        while True:
            # Get the most recent match
            match_str = match_queue.get_nowait()
            label.config(text=match_str)
    except queue.Empty:
        pass
    
    # Schedule next check
    root.after(100, check_queue, root, label, match_queue)

def main():
    print("Loading signatures from signatures.csv...")
    signatures_lookup = load_signatures('signatures.csv')
    print(f"Loaded {len(signatures_lookup)} values into lookup dictionary.")
    
    match_queue = queue.Queue()
    
    # Start scraper in a background thread
    t = threading.Thread(target=scraper_worker, args=(signatures_lookup, match_queue), daemon=True)
    t.start()
    
    if OVERLAY['enabled']:
        root = tk.Tk()
        # Remove window decorations (borderless)
        root.overrideredirect(True)
        # Keep window on top
        root.wm_attributes("-topmost", True)
        
        # Make the background color transparent (Windows only)
        # Black is a good transparent color key
        transparent_color = "black"
        root.wm_attributes("-transparentcolor", transparent_color)
        root.config(bg=transparent_color)
        
        # Make it click-through (ignores mouse events)
        root.wm_attributes("-disabled", True)
        
        # Position the window
        root.geometry(f"+{OVERLAY['x']}+{OVERLAY['y']}")
        
        label = tk.Label(root, text="[Overlay Active]", font=("Arial", OVERLAY['font_size'], "bold"), fg=OVERLAY['color'], bg=transparent_color)
        label.pack()
        
        # Check queue periodically
        root.after(100, check_queue, root, label, match_queue)
        
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass
    else:
        # If no overlay, just wait for thread to finish (which is never, unless interrupted)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    main()
