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

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=2
)
detector = HandLandmarker.create_from_options(options)

# ─── PyAutoGUI Settings ────────────────────────────────────────────────────────
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

# ─── Parameters ────────────────────────────────────────────────────────────────
MARGIN          = 100
PINCH_OPEN      = 55        # distance to consider "open" (hysteresis high)
PINCH_CLOSE     = 35        # distance to consider "closed" (hysteresis low)
SMOOTH          = 0.3
DRAG_DELAY      = 0.4       # seconds held before it becomes a drag (not a click)
RIGHT_COOLDOWN  = 0.5
SCROLL_SENS     = 400       # higher = faster scroll

# ─── State ─────────────────────────────────────────────────────────────────────
screen_w, screen_h = pyautogui.size()
cx, cy = pyautogui.position()
pos_buffer = deque(maxlen=6)

# Click state machine: OPEN → CLOSING → CLOSED → OPENING → OPEN
pinch_state     = "OPEN"    # OPEN | CLOSED
pinch_start_t   = None
is_dragging     = False
frozen_x        = None      # cursor X frozen during pinch
frozen_y        = None      # cursor Y frozen during pinch
last_right_t    = 0
prev_scroll_y   = None

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 60)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def lm_px(lm, w, h):
    return int(lm.x * w), int(lm.y * h)

def to_screen(lm, fw, fh):
    sx = (lm.x * fw - MARGIN) / (fw - 2 * MARGIN) * screen_w
    sy = (lm.y * fh - MARGIN) / (fh - 2 * MARGIN) * screen_h
    return max(0, min(screen_w - 1, sx)), max(0, min(screen_h - 1, sy))

def is_pinky_up(hand):
    return hand[20].y < hand[17].y - 0.04


while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]
    now = time.time()

    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB,
                      data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    results = detector.detect_for_video(mp_img, int(now * 1000))

    hud = []

    if results.hand_landmarks:
        sorted_hands = sorted(results.hand_landmarks,
                              key=lambda lms: lms[8].x, reverse=True)
        mh = sorted_hands[0]  # mouse hand (rightmost on screen)

        idx_px = lm_px(mh[8], fw, fh)
        thm_px = lm_px(mh[4], fw, fh)
        pinch_d = dist(idx_px, thm_px)

        # ── HYSTERESIS PINCH DETECTION ───────────────────────────────────────
        # Uses two thresholds so it doesn't flicker at the boundary
        if pinch_state == "OPEN" and pinch_d < PINCH_CLOSE:
            pinch_state  = "CLOSED"
            pinch_start_t = now
            # Freeze cursor at current position the moment pinch starts
            frozen_x, frozen_y = cx, cy

        elif pinch_state == "CLOSED" and pinch_d > PINCH_OPEN:
            held = now - pinch_start_t

            if is_dragging:
                pyautogui.mouseUp()
                is_dragging = False
                hud.append("DROP")
            elif held < DRAG_DELAY:
                # Short pinch = single click
                pyautogui.click(frozen_x, frozen_y)
                hud.append("CLICK!")

            pinch_state   = "OPEN"
            pinch_start_t = None
            frozen_x      = None
            frozen_y      = None

        # ── DRAG PROMOTION ───────────────────────────────────────────────────
        if pinch_state == "CLOSED" and not is_dragging:
            held = now - pinch_start_t
            if held >= DRAG_DELAY:
                pyautogui.mouseDown(frozen_x, frozen_y)
                is_dragging = True
                hud.append("DRAG")

        # ── CURSOR MOVEMENT (only when NOT pinching) ─────────────────────────
        if pinch_state == "OPEN":
            tx, ty = to_screen(mh[8], fw, fh)
            pos_buffer.append((tx, ty))

            weights = list(range(1, len(pos_buffer) + 1))
            wx = sum(p[0] * wt for p, wt in zip(pos_buffer, weights)) / sum(weights)
            wy = sum(p[1] * wt for p, wt in zip(pos_buffer, weights)) / sum(weights)

            cx = cx + (wx - cx) * SMOOTH
            cy = cy + (wy - cy) * SMOOTH
            cx = max(0, min(screen_w - 1, cx))
            cy = max(0, min(screen_h - 1, cy))
            pyautogui.moveTo(cx, cy, _pause=False)

        elif is_dragging:
            # While dragging: allow movement (don't freeze)
            tx, ty = to_screen(mh[8], fw, fh)
            pos_buffer.append((tx, ty))
            weights = list(range(1, len(pos_buffer) + 1))
            wx = sum(p[0] * wt for p, wt in zip(pos_buffer, weights)) / sum(weights)
            wy = sum(p[1] * wt for p, wt in zip(pos_buffer, weights)) / sum(weights)
            cx = cx + (wx - cx) * SMOOTH
            cy = cy + (wy - cy) * SMOOTH
            pyautogui.moveTo(cx, cy, _pause=False)
            hud.append("DRAGGING")

        # ── DRAW FEEDBACK ─────────────────────────────────────────────────────
        color = (0, 80, 255) if pinch_state == "CLOSED" else (0, 255, 80)
        cv2.circle(frame, idx_px, 14, color, cv2.FILLED)
        cv2.circle(frame, thm_px, 10, color, cv2.FILLED)
        cv2.line(frame, idx_px, thm_px, color, 2)

        # Pinch distance bar (visual feedback)
        bar_pct = max(0.0, min(1.0, 1 - (pinch_d - PINCH_CLOSE) / (PINCH_OPEN - PINCH_CLOSE)))
        bar_w = int(bar_pct * 120)
        cv2.rectangle(frame, (fw - 140, fh - 30), (fw - 20, fh - 10), (60, 60, 60), cv2.FILLED)
        cv2.rectangle(frame, (fw - 140, fh - 30), (fw - 140 + bar_w, fh - 10), color, cv2.FILLED)
        cv2.putText(frame, "PINCH", (fw - 140, fh - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # ── SECONDARY HAND ────────────────────────────────────────────────────
        if len(sorted_hands) > 1:
            ch = sorted_hands[1]
            c_idx = lm_px(ch[8], fw, fh)
            c_thm = lm_px(ch[4], fw, fh)

            if dist(c_idx, c_thm) < PINCH_CLOSE:
                if now - last_right_t > RIGHT_COOLDOWN:
                    pyautogui.rightClick()
                    last_right_t = now
                    hud.append("RIGHT CLICK")
                cv2.circle(frame, c_idx, 20, (255, 80, 0), cv2.FILLED)

            elif is_pinky_up(ch):
                curr_y = ch[8].y
                if prev_scroll_y is not None:
                    delta = (prev_scroll_y - curr_y) * SCROLL_SENS
                    if abs(delta) > 0.3:
                        pyautogui.scroll(int(delta))
                prev_scroll_y = curr_y
                hud.append("SCROLL")
                cv2.circle(frame, lm_px(ch[20], fw, fh), 10, (0, 220, 255), cv2.FILLED)
            else:
                prev_scroll_y = None

    else:
        # Safety: release if hands disappear
        if is_dragging:
            pyautogui.mouseUp()
            is_dragging = False
        pinch_state   = "OPEN"
        pinch_start_t = None
        frozen_x = frozen_y = None
        prev_scroll_y = None

    # ── HUD ──────────────────────────────────────────────────────────────────
    for i, line in enumerate(hud):
        cv2.putText(frame, line, (20, 40 + i * 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 180), 2)

    # Gesture guide
    guide = [
        "Right hand: move cursor",
        "Pinch (right): click / drag",
        "Pinch (left): right-click",
        "Pinky up (left): scroll",
        "ESC: quit"
    ]
    for i, g in enumerate(guide):
        cv2.putText(frame, g, (10, fh - 130 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)

    cv2.imshow("Hand Mouse v2", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

if is_dragging:
    pyautogui.mouseUp()
cap.release()
cv2.destroyAllWindows()