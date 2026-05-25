# Siggy: Signature Helper

This project is a Python-based screen scraping utility for use with Star Citizen where you want to instantly identify radar ping signatures without having to memorize the numeric values for different ores or materials.

It continuously captures a specific region of your screen, uses Optical Character Recognition (OCR) to read a numeric value, and matches it against a known list of signatures in `signatures.csv`. When a match is found, it displays the corresponding material name and tier as a click-through, transparent overlay on your screen.

## Features
- **Real-time OCR**: Captures a specified screen region twice a second.
- **Dynamic Lookup**: Maps numeric values to names, tiers, and multipliers using a `signatures.csv` file.
- **Transparent Overlay**: Uses an invisible, overlay to display the matched text seamlessly on top of your game.
- **Coordinate Helper**: Includes a helper in the GUI to easily find the exact screen coordinates to capture.

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

## Usage

Start the Siggy by running:
```bash
python siggy.py
```

- When the script starts, you may see a temporary **"[Overlay Active]"** message appear on your screen to confirm the overlay is working. 
- It will then continuously scan the configured region.
- When it reads a number that matches a value in `signatures.csv`, it will display the match on the overlay.
- If the number disappears or changes to an unknown value, the overlay will clear itself after 2 seconds.

To stop the script, press `Ctrl+C` in the terminal or close the GUI window.

## Troubleshooting

- **The overlay doesn't appear at all**: Ensure your game is set to **Windowed** or **Borderless Windowed / Windowed Fullscreen** mode. Standard Windows overlays cannot render on top of applications running in *Exclusive Fullscreen*.
- **Tesseract Error**: If you get a "tesseract is not installed or it's not in your PATH" error, double-check that the `tesseract_cmd` path in `scraper.py` perfectly matches the location of `tesseract.exe` on your hard drive.
