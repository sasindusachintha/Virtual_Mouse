import cv2
import pyautogui
import mediapipe as mp
import time
import math
from collections import deque

# ─── MediaPipe Setup ───────────────────────────────────────────────────────────
BaseOptions       = mp.tasks.BaseOptions
HandLandmarker    = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=2
)
detector = HandLandmarker.create_from_options(options)

# ─── PyAutoGUI Settings ────────────────────────────────────────────────────────
pyautogui.PAUSE    = 0
pyautogui.FAILSAFE = False

# ─── Tunable Parameters ────────────────────────────────────────────────────────
MARGIN          = 110     # Deadzone at screen edges (pixels)
PINCH_CLOSE     = 30      # Distance (px) to trigger pinch
PINCH_OPEN      = 45      # Distance (px) to release pinch (hysteresis gap)
SMOOTH          = 0.15    # Lerp factor: lower = smoother, higher = more responsive
DRAG_DELAY      = 0.25    # Seconds held before click becomes drag
RIGHT_COOLDOWN  = 0.5     # Seconds between right-clicks
SCROLL_SENS     = 500     # Scroll multiplier
HUD_DURATION    = 0.5     # Seconds to display HUD messages
TARGET_FPS      = 60      # Cap processing rate

# ─── State ─────────────────────────────────────────────────────────────────────
screen_w, screen_h = pyautogui.size()
pos_buffer   = deque(maxlen=5)
hud_messages = {}          # { label: expiry_timestamp }

state = {
    "cx": float(screen_w // 2),
    "cy": float(screen_h // 2),
    "pinch":        "OPEN",    # "OPEN" | "CLOSED"
    "pinch_start":  None,
    "dragging":     False,
    "frozen_x":     None,
    "frozen_y":     None,
    "last_right_t": 0.0,
    "prev_scroll_y": None,
    "prev_scroll_t": 0.0,
}

# ─── Helpers ───────────────────────────────────────────────────────────────────
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def lm_px(lm, w, h):
    return int(lm.x * w), int(lm.y * h)

def to_screen(lm, fw, fh):
    sx = (lm.x * fw - MARGIN) / (fw - 2 * MARGIN) * screen_w
    sy = (lm.y * fh - MARGIN) / (fh - 2 * MARGIN) * screen_h
    return max(0.0, min(screen_w - 1.0, sx)), max(0.0, min(screen_h - 1.0, sy))

def hand_scale(hand):
    """Wrist (0) to middle-finger MCP (9) distance as a normalisation factor."""
    dx = hand[0].x - hand[9].x
    dy = hand[0].y - hand[9].y
    return math.hypot(dx, dy) or 1e-6

def is_pinky_up(hand):
    """Scale-invariant pinky check."""
    scale = hand_scale(hand)
    return (hand[17].y - hand[20].y) / scale > 0.15

def weighted_avg(buf):
    weights = list(range(1, len(buf) + 1))
    total = sum(weights)
    wx = sum(p[0] * w for p, w in zip(buf, weights)) / total
    wy = sum(p[1] * w for p, w in zip(buf, weights)) / total
    return wx, wy

def hud_add(label, now):
    hud_messages[label] = now + HUD_DURATION

def hud_draw(frame, now):
    active = [(lbl, exp) for lbl, exp in hud_messages.items() if exp > now]
    hud_messages.clear()
    hud_messages.update(dict(active))
    for i, (lbl, _) in enumerate(active):
        cv2.putText(frame, lbl, (20, 50 + i * 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 200), 2)

# ─── Camera ────────────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

frame_interval = 1.0 / TARGET_FPS
last_frame_t   = 0.0

print("AI Air Mouse running — ESC to quit.")

# ─── Main Loop ─────────────────────────────────────────────────────────────────
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    now = time.time()

    # FPS cap
    if now - last_frame_t < frame_interval:
        if cv2.waitKey(1) & 0xFF == 27:
            break
        continue
    last_frame_t = now

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]

    mp_img  = mp.Image(image_format=mp.ImageFormat.SRGB,
                       data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    results = detector.detect_for_video(mp_img, int(now * 1_000_000))

    s = state   # shorthand alias

    if results.hand_landmarks:
        # Rightmost index fingertip on screen → mouse hand
        sorted_hands = sorted(results.hand_landmarks,
                               key=lambda lms: lms[8].x, reverse=True)
        mh = sorted_hands[0]

        idx_px  = lm_px(mh[8],  fw, fh)
        thm_px  = lm_px(mh[4],  fw, fh)
        pinch_d = dist(idx_px, thm_px)

        # ── 1. MOVEMENT ───────────────────────────────────────────────────────
        if s["pinch"] == "OPEN" or s["dragging"]:
            tx, ty = to_screen(mh[8], fw, fh)
            pos_buffer.append((tx, ty))
            wx, wy = weighted_avg(pos_buffer)
            s["cx"] += (wx - s["cx"]) * SMOOTH
            s["cy"] += (wy - s["cy"]) * SMOOTH
            pyautogui.moveTo(s["cx"], s["cy"], _pause=False)

        # ── 2. CLICK / DRAG ───────────────────────────────────────────────────
        if s["pinch"] == "OPEN" and pinch_d < PINCH_CLOSE:
            s["pinch"]       = "CLOSED"
            s["pinch_start"] = now
            s["frozen_x"]    = s["cx"]
            s["frozen_y"]    = s["cy"]

        elif s["pinch"] == "CLOSED":
            held = now - s["pinch_start"]

            if held >= DRAG_DELAY and not s["dragging"]:
                pyautogui.mouseDown(s["frozen_x"], s["frozen_y"])
                s["dragging"] = True
                hud_add("DRAG", now)

            if pinch_d > PINCH_OPEN:
                if s["dragging"]:
                    pyautogui.mouseUp()
                    s["dragging"] = False
                    hud_add("DROP", now)
                else:
                    pyautogui.click(s["frozen_x"], s["frozen_y"])
                    hud_add("CLICK!", now)
                s["pinch"]    = "OPEN"
                s["frozen_x"] = s["frozen_y"] = None

        # ── 3. LEFT HAND (right-click & scroll) ───────────────────────────────
        if len(sorted_hands) > 1:
            lh    = sorted_hands[1]
            l_idx = lm_px(lh[8], fw, fh)
            l_thm = lm_px(lh[4], fw, fh)

            if dist(l_idx, l_thm) < PINCH_CLOSE:
                if now - s["last_right_t"] > RIGHT_COOLDOWN:
                    pyautogui.rightClick()
                    s["last_right_t"] = now
                    hud_add("RIGHT CLICK", now)
                cv2.circle(frame, l_idx, 20, (255, 0, 0), cv2.FILLED)

            elif is_pinky_up(lh):
                curr_y = lh[8].y
                if s["prev_scroll_y"] is not None:
                    delta = (s["prev_scroll_y"] - curr_y) * SCROLL_SENS
                    if abs(delta) > 1:
                        pyautogui.scroll(int(delta))
                s["prev_scroll_y"] = curr_y
                s["prev_scroll_t"] = now
                hud_add("SCROLLING", now)
                cv2.circle(frame, lm_px(lh[20], fw, fh), 10, (0, 255, 255), cv2.FILLED)
            else:
                # Only reset scroll if pinky has been down for >2 frames
                if now - s["prev_scroll_t"] > 0.1:
                    s["prev_scroll_y"] = None

        # Visuals
        color = (0, 0, 255) if s["dragging"] else (0, 255, 0)
        cv2.circle(frame, idx_px, 12, color, cv2.FILLED)
        cv2.circle(frame, thm_px, 10, color, cv2.FILLED)

    else:
        # Safety reset when no hands detected
        if s["dragging"]:
            pyautogui.mouseUp()
            s["dragging"] = False
        s["pinch"]         = "OPEN"
        s["prev_scroll_y"] = None

    # ── HUD & Display ─────────────────────────────────────────────────────────
    hud_draw(frame, now)
    cv2.rectangle(frame, (MARGIN, MARGIN), (fw - MARGIN, fh - MARGIN),
                  (255, 255, 255), 1)
    cv2.imshow("AI Air Mouse", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

# ─── Cleanup ───────────────────────────────────────────────────────────────────
if s["dragging"]:
    pyautogui.mouseUp()
cap.release()
cv2.destroyAllWindows()