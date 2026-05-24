import time
from pynput import mouse

print("This script will help you find the coordinates for the screen capture.")
print("Instructions:")
print("1. Click on the TOP-LEFT corner of the region you want to capture.")
print("2. Click on the BOTTOM-RIGHT corner of the region you want to capture.")

clicks = []

def on_click(x, y, button, pressed):
    if pressed:
        clicks.append((int(x), int(y)))
        if len(clicks) == 1:
            print(f"Top-Left corner recorded at: {clicks[0]}")
        elif len(clicks) == 2:
            print(f"Bottom-Right corner recorded at: {clicks[1]}")
            
            x1, y1 = clicks[0]
            x2, y2 = clicks[1]
            
            top = min(y1, y2)
            left = min(x1, x2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            
            print("\n--- configuration for scraper.py ---")
            print(f"MONITOR = {{")
            print(f"    'top': {top},")
            print(f"    'left': {left},")
            print(f"    'width': {width},")
            print(f"    'height': {height}")
            print(f"}}")
            print("------------------------------------")
            
            return False # Stop listener

with mouse.Listener(on_click=on_click) as listener:
    listener.join()
