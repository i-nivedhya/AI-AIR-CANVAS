"""
✍️ Hand Math Solver — Draw equations with your fingers, solve & send via Email
Uses Groq (free & fast) for AI vision

GESTURES:
  - Pinch (index + thumb touch)     → Draw
  - Open Palm (all fingers spread)  → Erase under hand
  - Victory ✌️ (hold 1.5s)          → Solve & Email
  - Pinch on right strip (up/down)  → Increase / Decrease brush size
  - Pinch on palette                → Pick color
  - Q / Esc                         → Quit
  - C key                           → Clear canvas
  - S key                           → Solve (backup)
"""

import cv2
import numpy as np
import math
import re
import threading
import time
import os
import smtplib
import ssl
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

# ── MediaPipe ─────────────────────────────────────────────────────────────────
try:
    import mediapipe as mp
    MP_OK = True
except ImportError:
    print("[WARN] mediapipe not installed. Run: pip install mediapipe==0.10.14")
    MP_OK = False

# ── Groq ──────────────────────────────────────────────────────────────────────
try:
    from groq import Groq
    GROQ_OK = True
    print("[INFO] Groq available")
except ImportError:
    print("[WARN] groq not installed. Run: pip install groq")
    GROQ_OK = False

load_dotenv()

GROQ_KEY      = os.getenv("GROQ_API_KEY", "")
SEND_EMAIL    = os.getenv("SEND_EMAIL", "")
EMAIL_PASS    = os.getenv("EMAIL_PASSWORD", "")
RECEIVE_EMAIL = os.getenv("RECEIVE_EMAIL", "")

# ── Constants ─────────────────────────────────────────────────────────────────
PINCH_THRESHOLD   = 40
BRUSH_MIN         = 2
BRUSH_MAX         = 40
ERASER_RADIUS     = 30
CANVAS_ALPHA      = 0.75
VICTORY_HOLD_SECS = 1.5

SIZE_STRIP_W   = 50
SIZE_STRIP_PAD = 8

PALETTE = [
    ("White",   (255, 255, 255)),
    ("Yellow",  (0,   220, 255)),
    ("Green",   (0,   220,  80)),
    ("Cyan",    (255, 220,   0)),
    ("Red",     (50,   50, 255)),
    ("Magenta", (220,   0, 220)),
    ("Blue",    (255,  80,   0)),
    ("Orange",  (0,   140, 255)),
    ("Pink",    (180,  80, 255)),
]

SWATCH_H   = 52
SWATCH_W   = 60
SWATCH_PAD = 6
STATUS_H   = 36

WIN_NAME = "Hand Math Solver  [Q=quit]"


# ── Helpers ───────────────────────────────────────────────────────────────────
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def clean_math_text(text):
    """Convert LaTeX math notation to clean readable plain text."""
    text = re.sub(r'\$\$([^$]+)\$\$', r'\1', text)
    text = re.sub(r'\$([^$]+)\$',     r'\1', text)
    replacements = [
        (r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1/\2)'),
        (r'\\sqrt\{([^}]+)\}',            r'sqrt(\1)'),
        (r'\\sqrt',                        r'sqrt'),
        (r'\\times',                       r'x'),
        (r'\\div',                         r'/'),
        (r'\\pm',                          r'+/-'),
        (r'\\leq',                         r'<='),
        (r'\\geq',                         r'>='),
        (r'\\neq',                         r'!='),
        (r'\\approx',                      r'~='),
        (r'\\infty',                       r'infinity'),
        (r'\\pi',                          r'pi'),
        (r'\\alpha',                       r'alpha'),
        (r'\\beta',                        r'beta'),
        (r'\\theta',                       r'theta'),
        (r'\\cdot',                        r'*'),
        (r'\\left\(',                      r'('),
        (r'\\right\)',                     r')'),
        (r'\\left\[',                      r'['),
        (r'\\right\]',                     r']'),
        (r'\^2',                           r'^2'),
        (r'\^3',                           r'^3'),
        (r'\^\{([^}]+)\}',                r'^(\1)'),
        (r'_\{([^}]+)\}',                 r'_(\1)'),
        (r'\\[a-zA-Z]+',                   r''),
        (r'\{|\}',                         r''),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text.strip()


# ── Gesture detector ──────────────────────────────────────────────────────────
def detect_gesture(lm, W, H):
    """
    Returns: (gesture, index_tip, thumb_tip)
    Gestures: 'pinch', 'palm', 'victory', 'none'
    """
    thumb_tip = (int(lm[4].x * W), int(lm[4].y * H))
    index_tip = (int(lm[8].x * W), int(lm[8].y * H))

    if dist(thumb_tip, index_tip) < PINCH_THRESHOLD:
        return 'pinch', index_tip, thumb_tip

    tips = [8,  12, 16, 20]
    pips = [6,  10, 14, 18]
    fingers_up = sum(1 for tip, pip in zip(tips, pips) if lm[tip].y < lm[pip].y)

    is_right_hand = lm[0].x < lm[9].x
    thumb_up  = (lm[4].x < lm[3].x) if is_right_hand else (lm[4].x > lm[3].x)
    total_up  = fingers_up + (1 if thumb_up else 0)

    if total_up >= 4:
        return 'palm', index_tip, thumb_tip

    index_up   = lm[8].y  < lm[6].y
    middle_up  = lm[12].y < lm[10].y
    ring_down  = lm[16].y > lm[14].y
    pinky_down = lm[20].y > lm[18].y

    if index_up and middle_up and ring_down and pinky_down:
        return 'victory', index_tip, thumb_tip

    return 'none', index_tip, thumb_tip


# ── Groq Vision solver ────────────────────────────────────────────────────────
def solve_equation(image_bgr):
    if not GROQ_OK or not GROQ_KEY:
        return "Groq not configured", "N/A", "Set GROQ_API_KEY in .env"

    try:
        _, buf  = cv2.imencode(".png", image_bgr)
        img_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        client = Groq(api_key=GROQ_KEY)

        prompt = (
            "Look at this handwritten image carefully.\n\n"
            "STEP 1 — READ: Identify ALL equations or expressions written in the image. "
            "There may be one equation or a SYSTEM of multiple equations (e.g. two linear equations). "
            "Read every line of handwriting — do not skip any equation.\n\n"
            "STEP 2 — CLASSIFY:\n"
            "  - If there is ONE equation: solve it for the unknown variable.\n"
            "  - If there are TWO OR MORE equations: treat them as a SYSTEM and solve simultaneously "
            "for ALL variables (e.g. find both x and y).\n\n"
            "STEP 3 — SOLVE: Work step by step, clearly. Do NOT skip steps. "
            "Do NOT second-guess yourself mid-solution.\n\n"
            "STEP 4 — VERIFY: Substitute ALL found values back into EVERY original equation "
            "and confirm both sides are equal. Show the substitution numerically.\n\n"
            "STEP 5 — If verification fails for any equation, redo from scratch silently "
            "and only output the corrected solution.\n\n"
            "Reply in this EXACT format with no extra text outside it:\n"
            "EQUATION: <all equations exactly as written, separated by  |  if multiple>\n"
            "ANSWER: <all variable values, e.g. x=2, y=3>\n"
            "STEPS: <clean numbered steps + verification of ALL equations at the end>"
        )

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=500
        )

        text = response.choices[0].message.content.strip()
        print(f"[Groq] Response:\n{text}")

        equation = answer = "Unknown"
        for line in text.splitlines():
            if line.startswith("EQUATION:"):
                equation = line.replace("EQUATION:", "").strip()
            elif line.startswith("ANSWER:"):
                answer = line.replace("ANSWER:", "").strip()

        return equation, answer, text

    except Exception as e:
        err = str(e)
        print(f"[Groq] Error: {err}")
        return "Error", err[:80], err


# ── Independent math verifier ─────────────────────────────────────────────────
def verify_answer(equation, answer, steps):
    if not GROQ_OK or not GROQ_KEY:
        return True, answer, steps

    try:
        client = Groq(api_key=GROQ_KEY)

        prompt = (
            f"You are a strict math checker.\n"
            f"Given these equation(s): {equation}\n"
            f"And this claimed answer: {answer}\n\n"
            f"1. Independently solve the equation(s) yourself from scratch.\n"
            f"   If there are multiple equations, solve them as a SYSTEM simultaneously.\n"
            f"2. Substitute ALL your found values back into EVERY original equation "
            f"and confirm each one is satisfied numerically.\n"
            f"3. Check if the claimed answer matches your verified answer.\n\n"
            f"Reply in this EXACT format:\n"
            f"CORRECT: yes or no\n"
            f"VERIFIED_ANSWER: <all correct variable values, e.g. x=2, y=3>\n"
            f"VERIFICATION: <show substitution into each equation proving correctness>"
        )

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )

        text = response.choices[0].message.content.strip()
        print(f"[Verifier] Response:\n{text}")

        is_correct      = True
        verified_answer = answer
        verification    = steps

        for line in text.splitlines():
            if line.startswith("CORRECT:"):
                val = line.replace("CORRECT:", "").strip().lower()
                is_correct = (val == "yes")
            elif line.startswith("VERIFIED_ANSWER:"):
                verified_answer = line.replace("VERIFIED_ANSWER:", "").strip()
            elif line.startswith("VERIFICATION:"):
                verification = line.replace("VERIFICATION:", "").strip()

        return is_correct, verified_answer, verification

    except Exception as e:
        print(f"[Verifier] Error: {e}")
        return True, answer, steps


# ── Plain-text Email sender ───────────────────────────────────────────────────
def send_email(equation, answer, full_response):
    if not SEND_EMAIL or not EMAIL_PASS or not RECEIVE_EMAIL:
        print("[Email] Not configured in .env")
        return False

    try:
        eq_clean   = clean_math_text(equation)
        ans_clean  = clean_math_text(answer)
        full_clean = clean_math_text(full_response)

        body = (
            f"Hand-Written Math Solver — Result\n"
            f"{'=' * 45}\n\n"
            f"Question   : {eq_clean}\n\n"
            f"Answer     : {ans_clean}\n\n"
            f"Explanation:\n"
            f"{'-' * 45}\n"
            f"{full_clean}\n"
            f"{'-' * 45}\n\n"
            f"Date & Time: {datetime.now().strftime('%d %B %Y  %I:%M %p')}\n\n"
            f"Generated by Hand Math Solver — AI powered by Groq\n"
        )

        msg            = MIMEMultipart()
        msg["Subject"] = f"Hand Math: {eq_clean} = {ans_clean}"
        msg["From"]    = SEND_EMAIL
        msg["To"]      = RECEIVE_EMAIL
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SEND_EMAIL, EMAIL_PASS)
            server.sendmail(SEND_EMAIL, RECEIVE_EMAIL, msg.as_string())

        print(f"[Email] Sent to {RECEIVE_EMAIL}!")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[Email] Auth failed! Use Gmail App Password.")
        return False
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False


# ── Size-strip UI renderer ────────────────────────────────────────────────────
def draw_size_strip(out, brush_r, H, swatch_h, status_h, W):
    strip_x1     = W - SIZE_STRIP_W
    strip_x2     = W
    strip_top    = swatch_h + SIZE_STRIP_PAD
    strip_bottom = H - status_h - SIZE_STRIP_PAD
    strip_height = strip_bottom - strip_top

    cv2.rectangle(out, (strip_x1, strip_top), (strip_x2, strip_bottom), (30, 30, 30), -1)
    cv2.rectangle(out, (strip_x1, strip_top), (strip_x2, strip_bottom), (80, 80, 80),  1)

    ratio    = (brush_r - BRUSH_MIN) / max(BRUSH_MAX - BRUSH_MIN, 1)
    fill_h   = int(ratio * strip_height)
    fill_top = strip_bottom - fill_h
    cv2.rectangle(out, (strip_x1 + 2, fill_top), (strip_x2 - 2, strip_bottom), (0, 200, 120), -1)

    mid_y = (strip_top + strip_bottom) // 2
    mid_x = strip_x1 + SIZE_STRIP_W // 2
    cv2.circle(out, (mid_x, mid_y), max(1, brush_r // 2), (255, 255, 255), -1)

    cv2.putText(out, "SIZE", (strip_x1 + 4, strip_top - 4),   cv2.FONT_HERSHEY_SIMPLEX, 0.32, (160, 160, 160), 1)
    cv2.putText(out, str(brush_r), (strip_x1 + 8, strip_bottom + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
    cv2.putText(out, "+", (strip_x1 + 18, strip_top + 14),    cv2.FONT_HERSHEY_SIMPLEX, 0.5,  (180, 180, 180), 1)
    cv2.putText(out, "-", (strip_x1 + 20, strip_bottom - 5),  cv2.FONT_HERSHEY_SIMPLEX, 0.6,  (180, 180, 180), 1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not MP_OK:
        print("MediaPipe required. Run: pip install mediapipe==0.10.14")
        return
    if not GROQ_OK:
        print("Groq required. Run: pip install groq")
        return
    if not GROQ_KEY:
        print("GROQ_API_KEY missing in .env!")
        return

    try:
        detector = mp.solutions.hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.6,
        )
        print("[INFO] MediaPipe Hands ready.")
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open webcam.")
        return

    ret, frame = cap.read()
    if not ret:
        cap.release()
        return

    H, W   = frame.shape[:2]
    canvas = np.zeros((H, W, 3), dtype=np.uint8)

    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    current_color      = PALETTE[4][1]   # Red default
    brush_r            = 6
    prev_point         = None
    is_pinching        = False
    status_msg         = "Pinch=Draw | Palm=Erase | Hold V 1.5s=Solve | R-Strip=BrushSize"
    status_color       = (200, 200, 200)
    solving            = False
    victory_triggered  = False
    victory_start_time = None
    size_pinch_last_y  = None

    GESTURE_UI = {
        'pinch':   ("● DRAW",     (0,   255,  80)),
        'palm':    ("✋ ERASE",    (0,   120, 255)),
        'victory': ("✌ SOLVE",    (0,   255, 160)),
        'none':    ("○ idle",     (120, 120, 120)),
    }

    def in_canvas(x, y):
        return x < W - SIZE_STRIP_W and SWATCH_H <= y <= H - STATUS_H

    def in_size_strip(x, y):
        return W - SIZE_STRIP_W <= x <= W and SWATCH_H <= y <= H - STATUS_H

    def solve_async(snap):
        nonlocal solving, status_msg, status_color
        solving      = True
        status_msg   = "Solving with Groq AI..."
        status_color = (0, 200, 255)

        eq, ans, full = solve_equation(snap)

        if eq == "Error":
            status_msg   = f"AI Error: {ans[:70]}"
            status_color = (0, 50, 255)
            solving      = False
            return

        status_msg   = "Verifying answer..."
        status_color = (0, 180, 255)

        is_correct, verified_ans, verification = verify_answer(eq, ans, full)

        if not is_correct:
            final_ans  = verified_ans
            final_full = (
                f"{full}\n\n"
                f"--- VERIFICATION FAILED ---\n"
                f"Original answer '{clean_math_text(ans)}' was WRONG.\n"
                f"Corrected answer: {clean_math_text(verified_ans)}\n"
                f"Verification: {verification}"
            )
            status_color = (0, 80, 255)
        else:
            final_ans  = verified_ans
            final_full = f"{full}\n\nVerification: {verification}"
            status_color = (0, 255, 120)

        status_msg = f"Verified: {clean_math_text(eq)} = {clean_math_text(final_ans)}  |  Sending..."

        ok = send_email(eq, final_ans, final_full)

        if ok:
            status_msg   = f"Email sent!  {clean_math_text(eq)} = {clean_math_text(final_ans)}"
            status_color = (0, 255, 80)
        else:
            status_msg   = f"Solved: {clean_math_text(eq)} = {clean_math_text(final_ans)}  (check email config)"
            status_color = (0, 200, 255)

        solving = False

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)

        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = detector.process(rgb)

        gesture   = 'none'
        index_pt  = None
        thumb_pt  = None
        pinch_now = False

        # ── Hand landmark processing ──────────────────────────────────────────
        if result.multi_hand_landmarks:
            lm = result.multi_hand_landmarks[0].landmark
            gesture, index_pt, thumb_pt = detect_gesture(lm, W, H)
            pinch_now = (gesture == 'pinch')

            # ── Visual feedback ───────────────────────────────────────────────
            if gesture == 'pinch':
                cv2.circle(frame, index_pt, 10, (0, 255, 0), -1)
                cv2.circle(frame, thumb_pt,  7, (0, 255, 0),  2)
                mid = ((thumb_pt[0] + index_pt[0]) // 2,
                       (thumb_pt[1] + index_pt[1]) // 2)
                cv2.circle(frame, mid, 14, current_color, 2)

            elif gesture == 'palm':
                cx, cy = index_pt
                cv2.circle(frame, (cx, cy), ERASER_RADIUS, (0, 100, 255), 2)
                cv2.putText(frame, "ERASE",
                            (cx - 30, cy - ERASER_RADIUS - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 100, 255), 2)

            elif gesture == 'victory':
                cx = int(lm[9].x * W)
                cy = int(lm[9].y * H)
                cv2.circle(frame, (cx, cy), 36, (0, 255, 140), 3)
                cv2.putText(frame, "SOLVE!",
                            (cx - 38, cy - 44),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 140), 2)
                cv2.circle(frame, index_pt, 10, (0, 255, 140), -1)
                tip12 = (int(lm[12].x * W), int(lm[12].y * H))
                cv2.circle(frame, tip12, 10, (0, 255, 140), -1)

            else:
                if index_pt:
                    cv2.circle(frame, index_pt, 8, (200, 200, 200), -1)
                if thumb_pt:
                    cv2.circle(frame, thumb_pt, 6, (200, 200, 200),  2)

            # ── Victory → Solve: must hold for VICTORY_HOLD_SECS ─────────────
            if gesture == 'victory' and not solving:
                if victory_start_time is None:
                    victory_start_time = time.time()

                held      = time.time() - victory_start_time
                remaining = VICTORY_HOLD_SECS - held

                if not victory_triggered:
                    if remaining > 0:
                        cx = int(lm[9].x * W)
                        cy = int(lm[9].y * H)
                        progress = held / VICTORY_HOLD_SECS
                        cv2.ellipse(frame, (cx, cy), (44, 44), -90,
                                    0, int(360 * progress), (0, 255, 140), 3)
                        if not solving:
                            status_msg   = f"Hold V to solve... {remaining:.1f}s"
                            status_color = (0, 220, 140)
                    else:
                        victory_triggered = True
                        threading.Thread(
                            target=solve_async, args=(canvas.copy(),), daemon=True
                        ).start()
                        prev_point = None
            else:
                victory_start_time = None
                victory_triggered  = False

            # ── Palm → Erase (only when ink exists under hand) ────────────────
            if gesture == 'palm' and index_pt:
                ix, iy = index_pt
                if in_canvas(ix, iy):
                    x1 = max(0, ix - ERASER_RADIUS)
                    x2 = min(W, ix + ERASER_RADIUS)
                    y1 = max(0, iy - ERASER_RADIUS)
                    y2 = min(H, iy + ERASER_RADIUS)
                    has_ink = np.any(canvas[y1:y2, x1:x2] > 0)
                    if has_ink:
                        cv2.circle(canvas, (ix, iy), ERASER_RADIUS, (0, 0, 0), -1)
                        if not solving:
                            status_msg   = "Erasing..."
                            status_color = (0, 100, 255)

        # ── Size strip: pinch + move up/down ──────────────────────────────────
        on_strip = (index_pt is not None and pinch_now
                    and in_size_strip(index_pt[0], index_pt[1]))

        if on_strip:
            iy = index_pt[1]
            if size_pinch_last_y is not None:
                delta = size_pinch_last_y - iy
                if abs(delta) >= 3:
                    brush_r = int(np.clip(brush_r + delta * 0.18, BRUSH_MIN, BRUSH_MAX))
                    size_pinch_last_y = iy
                    if not solving:
                        status_msg   = f"Brush size: {brush_r}"
                        status_color = (0, 200, 120)
            else:
                size_pinch_last_y = iy
            prev_point = None
        else:
            size_pinch_last_y = None

        # ── Palette color pick (pinch in top palette bar) ─────────────────────
        if index_pt and pinch_now and index_pt[1] < SWATCH_H:
            ix = index_pt[0]
            for si, (name, col) in enumerate(PALETTE):
                sx1 = SWATCH_PAD + si * (SWATCH_W + SWATCH_PAD)
                if sx1 <= ix <= sx1 + SWATCH_W:
                    current_color = col
                    status_msg    = f"Color: {name}"
                    status_color  = col
                    prev_point    = None
                    pinch_now     = False
                    break

        # ── Draw on canvas ────────────────────────────────────────────────────
        if index_pt and pinch_now and not on_strip:
            ix, iy = index_pt
            if in_canvas(ix, iy):
                if is_pinching and prev_point:
                    cv2.line(canvas, prev_point, (ix, iy),
                             current_color, brush_r * 2)
                else:
                    cv2.circle(canvas, (ix, iy), brush_r, current_color, -1)
                prev_point = (ix, iy)
        elif not on_strip:
            prev_point = None

        is_pinching = pinch_now

        # ── Compose final frame ───────────────────────────────────────────────
        out     = frame.copy()
        mask    = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
        mask3   = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) / 255.0
        out_f   = out.astype(float)
        out_f   = (out_f * (1 - mask3 * CANVAS_ALPHA)
                   + canvas.astype(float) * mask3 * CANVAS_ALPHA)
        out     = np.clip(out_f, 0, 255).astype(np.uint8)

        # ── Palette bar ───────────────────────────────────────────────────────
        cv2.rectangle(out, (0, 0), (W, SWATCH_H), (20, 20, 20), -1)
        cv2.line(out, (0, SWATCH_H), (W, SWATCH_H), (60, 60, 60), 1)
        for si, (_, col) in enumerate(PALETTE):
            sx1 = SWATCH_PAD + si * (SWATCH_W + SWATCH_PAD)
            sx2 = sx1 + SWATCH_W
            cv2.rectangle(out, (sx1, 6), (sx2, SWATCH_H - 6), col, -1)
            if col == current_color:
                cv2.rectangle(out, (sx1-2, 4), (sx2+2, SWATCH_H-4),
                              (255, 255, 255), 2)

        ci_x = SWATCH_PAD + len(PALETTE) * (SWATCH_W + SWATCH_PAD) + 10
        if ci_x + 34 < W - SIZE_STRIP_W:
            cv2.rectangle(out, (ci_x, 8), (ci_x+34, SWATCH_H-8), current_color, -1)
            cv2.putText(out, "Active", (ci_x + 36, SWATCH_H - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 160), 1)

        # ── Size strip UI ─────────────────────────────────────────────────────
        draw_size_strip(out, brush_r, H, SWATCH_H, STATUS_H, W)

        # ── Gesture legend (top-left, black background) ───────────────────────
        legend_lines = [
            "Pinch  = Draw",
            "Palm   = Erase",
            "Hold V = Solve",
            "R-Side = BrushSz",
        ]
        leg_x  = 6
        leg_y0 = SWATCH_H + 16
        leg_lh = 18
        leg_w  = 155
        leg_h  = len(legend_lines) * leg_lh + 4
        cv2.rectangle(out, (leg_x - 2, leg_y0 - 14),
                      (leg_x + leg_w, leg_y0 + leg_h - 8), (0, 0, 0), -1)
        cv2.rectangle(out, (leg_x - 2, leg_y0 - 14),
                      (leg_x + leg_w, leg_y0 + leg_h - 8), (60, 60, 60), 1)
        for i, txt in enumerate(legend_lines):
            cv2.putText(out, txt, (leg_x, leg_y0 + i * leg_lh),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (20, 20, 20), 2, cv2.LINE_AA)
            cv2.putText(out, txt, (leg_x, leg_y0 + i * leg_lh),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (230, 230, 230), 1, cv2.LINE_AA)

        # ── Status bar ────────────────────────────────────────────────────────
        sb_y = H - STATUS_H
        cv2.rectangle(out, (0, sb_y), (W, H), (18, 18, 18), -1)
        cv2.line(out, (0, sb_y), (W, sb_y), (50, 50, 50), 1)

        g_text, g_col = GESTURE_UI.get(gesture, ("○ idle", (120, 120, 120)))
        cv2.putText(out, g_text, (10, H - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, g_col, 2, cv2.LINE_AA)
        cv2.putText(out, status_msg, (150, H - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, status_color, 1, cv2.LINE_AA)

        cv2.imshow(WIN_NAME, out)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord('c'):
            canvas[:] = 0
            status_msg   = "Canvas cleared"
            status_color = (180, 180, 180)
        elif key == ord('s') and not solving:
            threading.Thread(
                target=solve_async, args=(canvas.copy(),), daemon=True
            ).start()

    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print("Done.")


if __name__ == "__main__":
    main()