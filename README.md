# Siggy: Screen Signature Pinger & Overlay

This project is a Python-based screen scraping utility that continuously captures a specific region of your screen, uses Optical Character Recognition (OCR) to read a numeric value, and matches it against a known list of signatures in `signatures.csv`. When a match is found, it displays the corresponding material name and tier as a click-through, transparent overlay on your screen.

It is particularly useful for games (like Star Citizen) where you want to instantly identify radar ping signatures without having to memorize the numeric values for different ores or materials.

## Features
- **Real-time OCR**: Captures a specified screen region twice a second.
- **Dynamic Lookup**: Maps numeric values to names, tiers, and multipliers using a `signatures.csv` file.
- **Transparent Overlay**: Uses an invisible, click-through overlay to display the matched text seamlessly on top of your game.
- **Coordinate Helper**: Includes a helper script to easily find the exact screen coordinates to capture.

## Prerequisites

### 1. Python 3
Ensure you have Python 3 installed on your system. 

### 2. Tesseract OCR Engine
The script relies on `pytesseract`, which requires the Tesseract OCR engine to be installed on your machine.
- Download the Windows installer from the [UB-Mannheim Tesseract Project](https://github.com/UB-Mannheim/tesseract/wiki).
- Install it (the default path is usually `C:\Program Files\Tesseract-OCR\tesseract.exe`).

### 3. Python Dependencies
Install the required Python packages by running:
```bash
pip install -r requirements.txt
```
*(Packages include: `mss`, `opencv-python`, `pytesseract`, `pynput`)*

## Setup & Configuration

### Step 1: Find Your Screen Coordinates
You need to tell the scraper exactly where on your screen the number appears.
1. Run the helper script:
   ```bash
   python find_coords.py
   ```
2. Click the **Top-Left** corner of the number you want to scan.
3. Click the **Bottom-Right** corner of the number.
4. The script will output a dictionary (e.g., `{'top': 715, 'left': 1904, 'width': 118, 'height': 34}`). Copy this output.

### Step 2: Configure the Scraper
1. Open `scraper.py` in a text editor.
2. Replace the `MONITOR` dictionary at the top of the file with the one you generated in Step 1.
3. Check the Tesseract installation path. If you installed Tesseract somewhere other than `C:\Program Files\Tesseract-OCR\tesseract.exe`, update the `pytesseract.pytesseract.tesseract_cmd` path.
4. (Optional) Customize the overlay settings in the `OVERLAY` dictionary to change the font size, color, and position of the text on your screen.

## Usage

Start the scraper by running:
```bash
python scraper.py
```

- When the script starts, you will see a temporary **"[Overlay Active]"** message appear on your screen to confirm the overlay is working. 
- It will then continuously scan the configured region.
- When it reads a number that matches a value in `signatures.csv`, it will display the match on the overlay.
- If the number disappears or changes to an unknown value, the overlay will clear itself after 2 seconds.

To stop the script, press `Ctrl+C` in the terminal.

## Troubleshooting

- **The overlay doesn't appear at all**: Ensure your game is set to **Windowed** or **Borderless Windowed / Windowed Fullscreen** mode. Standard Windows overlays cannot render on top of applications running in *Exclusive Fullscreen*.
- **The text stays "[Overlay Active]" forever**: This means the script hasn't successfully read a matching number yet. Check your `MONITOR` coordinates to ensure it's capturing the right area.
- **The OCR is misreading numbers**: You may need to tweak the image preprocessing settings. Open `scraper.py` and modify the OpenCV `cv2.threshold` parameters inside the `preprocess_image()` function to better suit the text color and background of your game.
- **Tesseract Error**: If you get a "tesseract is not installed or it's not in your PATH" error, double-check that the `tesseract_cmd` path in `scraper.py` perfectly matches the location of `tesseract.exe` on your hard drive.
