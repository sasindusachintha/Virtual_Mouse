# Virtual Mouse

![Python](https://img.shields.io/badge/Python-3.10-blue)
![OpenCV](https://img.shields.io/badge/OpenCV-4.13.0-brightgreen)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.32-orange)

A **hand gesture-controlled virtual mouse** using Python, MediaPipe, and PyAutoGUI. Move your mouse cursor, click, drag, right-click, and scroll using hand gestures in front of your webcam — no physical mouse required!

---

## Features

- **Cursor Movement**: Move the mouse with your right hand.  
- **Left Click / Drag**: Pinch thumb and index finger to click or hold for drag.  
- **Right Click**: Pinch with the left hand.  
- **Scroll**: Raise pinky finger of left hand to scroll up/down.  
- **Smooth Cursor Movement**: Built-in smoothing for stable control.  
- **Visual Feedback**: On-screen HUD shows pinch, drag, right-click, and scroll gestures.

---

## Demo

![Virtual Mouse Demo](link-to-your-gif-or-screenshot)

---

## Installation

1. Clone the repository:
git clone https://github.com/sasindusachintha/Virtual_Mouse.git

2. Install dependencies:
- python -m pip install --upgrade pip
- pip install -r requirements.txt

## Usage
1. Connect a webcam to your PC.
2. Run the virtual mouse script:
- (open cmd in project folder and type command below "python hand_mouse.py".)
4. Use gestures as explained:
- Right hand pinch (thumb + index) :- 	      Click / Drag
- Left hand pinch:- 	                        Right-click
- Left hand pinky up:- 	                    Scroll
- ESC:- 	                                    Quit application

## Requirements
- Python 3.10
- OpenCV 4.13
- MediaPipe 0.10.32
- PyAutoGUI 0.9.54
- NumPy 2.x

All dependencies are listed in requirements.txt.

---

## Notes / Tips
- Make sure your hand is well-lit and visible to the webcam for accurate detection.
- Smooth cursor movement may take a few frames to respond initially.
- Keep your hands within the camera frame and avoid fast rapid movements.
- Adjust the parameters in hand_mouse.py for pinch sensitivity and screen mapping if needed.

---

## License
This project is released under the MIT License. See [LICENSE](LICENSE)
for details.

---
## Author
Sasindu Sachintha
GitHub: https://github.com/sasindusachintha

---
