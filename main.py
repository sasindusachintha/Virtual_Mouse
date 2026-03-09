import cv2
import pyautogui
import mediapipe as mp
import time
import math
from collections import deque

# ─── MediaPipe Setup ───────────────────────────────────────────────────────────
BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Make sure 'hand_landmarker.task' is in your folder!
options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=2
)
detector = HandLandmarker.create_from_options(options)

# ─── PyAutoGUI Settings ────────────────────────────────────────────────────────
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

# ─── Parameters (Optimized for Stability) ──────────────────────────────────────
MARGIN          = 110       # Deadzone at screen edges
PINCH_CLOSE     = 30        # Distance to trigger click
PINCH_OPEN      = 45        # Distance to release click (Hysteresis)
SMOOTH          = 0.15      # Lower = smoother, Higher = faster
DRAG_DELAY      = 0.25      # Seconds held before "Click" becomes "Drag"
RIGHT_COOLDOWN  = 0.5       
SCROLL_SENS     = 500       

# ─── State Variables ───────────────────────────────────────────────────────────
screen_w, screen_h = pyautogui.size()
cx, cy = pyautogui.position()
pos_buffer = deque(maxlen=5)

pinch_state     = "OPEN"    # OPEN | CLOSED
pinch_start_t   = None
is_dragging     = False
frozen_x, frozen_y = None, None
last_right_t    = 0
prev_scroll_y   = None

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def lm_px(lm, w, h):
    return int(lm.x * w), int(lm.y * h)

def to_screen(lm, fw, fh):
    sx = (lm.x * fw - MARGIN) / (fw - 2 * MARGIN) * screen_w
    sy = (lm.y * fh - MARGIN) / (fh - 2 * MARGIN) * screen_h
    return max(0, min(screen_w - 1, sx)), max(0, min(screen_h - 1, sy))

def is_pinky_up(hand):
    # Pinky tip (20) vs Pinky base (17)
    return hand[20].y < hand[17].y - 0.05

print("Starting AI Mouse... Press ESC to quit.")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]
    now = time.time()

    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, 
                      data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    results = detector.detect_for_video(mp_img, int(now * 1000))

    hud = []

    if results.hand_landmarks:
        # Sort hands: Rightmost hand on screen is the Mouse hand
        sorted_hands = sorted(results.hand_landmarks, key=lambda lms: lms[8].x, reverse=True)
        mh = sorted_hands[0]  

        idx_px = lm_px(mh[8], fw, fh)
        thm_px = lm_px(mh[4], fw, fh)
        mid_px = lm_px(mh[12], fw, fh)
        pinch_d = dist(idx_px, thm_px)

        # ── 1. MOVEMENT LOGIC (Right Hand) ───────────────────────────────────
        if pinch_state == "OPEN":
            tx, ty = to_screen(mh[8], fw, fh)
            pos_buffer.append((tx, ty))
            
            # Weighted average for extra stability
            weights = list(range(1, len(pos_buffer) + 1))
            wx = sum(p[0] * wt for p, wt in zip(pos_buffer, weights)) / sum(weights)
            wy = sum(p[1] * wt for p, wt in zip(pos_buffer, weights)) / sum(weights)

            cx = cx + (wx - cx) * SMOOTH
            cy = cy + (wy - cy) * SMOOTH
            pyautogui.moveTo(cx, cy, _pause=False)
        
        elif is_dragging:
            # Allow movement while dragging
            tx, ty = to_screen(mh[8], fw, fh)
            cx = cx + (tx - cx) * SMOOTH
            cy = cy + (ty - cy) * SMOOTH
            pyautogui.moveTo(cx, cy, _pause=False)

        # ── 2. CLICK / DRAG LOGIC (Right Hand) ──────────────────────────────
        if pinch_state == "OPEN" and pinch_d < PINCH_CLOSE:
            pinch_state = "CLOSED"
            pinch_start_t = now
            frozen_x, frozen_y = cx, cy # Lock position for clean click

        elif pinch_state == "CLOSED":
            held = now - pinch_start_t
            
            # Promote to Drag if held
            if held >= DRAG_DELAY and not is_dragging:
                pyautogui.mouseDown(frozen_x, frozen_y)
                is_dragging = True

            # Release
            if pinch_d > PINCH_OPEN:
                if is_dragging:
                    pyautogui.mouseUp()
                    is_dragging = False
                    hud.append("DROP")
                else:
                    pyautogui.click(frozen_x, frozen_y)
                    hud.append("CLICK!")
                
                pinch_state = "OPEN"
                frozen_x = frozen_y = None

        # ── 3. SECONDARY HAND (Left Hand) ────────────────────────────────────
        if len(sorted_hands) > 1:
            lh = sorted_hands[1]
            l_idx = lm_px(lh[8], fw, fh)
            l_thm = lm_px(lh[4], fw, fh)

            # Right Click (Left Index Pinch)
            if dist(l_idx, l_thm) < PINCH_CLOSE:
                if now - last_right_t > RIGHT_COOLDOWN:
                    pyautogui.rightClick()
                    last_right_t = now
                    hud.append("RIGHT CLICK")
                cv2.circle(frame, l_idx, 20, (255, 0, 0), cv2.FILLED)

            # Scroll (Left Pinky Up)
            elif is_pinky_up(lh):
                curr_y = lh[8].y
                if prev_scroll_y is not None:
                    delta = (prev_scroll_y - curr_y) * SCROLL_SENS
                    if abs(delta) > 1:
                        pyautogui.scroll(int(delta))
                prev_scroll_y = curr_y
                hud.append("SCROLLING")
                cv2.circle(frame, lm_px(lh[20], fw, fh), 10, (0, 255, 255), cv2.FILLED)
            else:
                prev_scroll_y = None

        # Visuals
        color = (0, 0, 255) if is_dragging else (0, 255, 0)
        cv2.circle(frame, idx_px, 12, color, cv2.FILLED)
        cv2.circle(frame, thm_px, 10, color, cv2.FILLED)

    else:
        # Safety reset
        if is_dragging:
            pyautogui.mouseUp()
            is_dragging = False
        pinch_state = "OPEN"

    # ── HUD & GUI ────────────────────────────────────────────────────────────
    for i, line in enumerate(hud):
        cv2.putText(frame, line, (20, 50 + i * 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 200), 2)

    cv2.rectangle(frame, (MARGIN, MARGIN), (fw-MARGIN, fh-MARGIN), (255, 255, 255), 1)
    cv2.imshow("Pro AI Air Mouse", frame)
    if cv2.waitKey(1) & 0xFF == 27: break

cap.release()
cv2.destroyAllWindows()