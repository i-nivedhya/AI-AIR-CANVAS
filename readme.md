# AI Air Canvas 🎯

## Basic Details

**Team Name:** Innovature

### Team Members

- **Member 1:** Nivedhya Unnikannan - Muthoot Institute of Technology and Science
- **Member 2:** Amina K A - Muthoot Institute of Technology and Science

### Hosted Project Link

[mention your project hosted link here]

---

## Project Description

AI Air Canvas is a real time gesture controlled drawing application that lets users draw in the air using hand gestures captured via webcam. Users can write mathematical equations in the air, trigger an AI solver to compute the answer instantly, and automatically receive the verified solution directly to their registered email all without touching a keyboard or mouse.

---

## The Problem Statement

Traditional learning and problem-solving tools require physical input devices like keyboards, mice, or styluses. There is no intuitive, hands-free way to sketch ideas or solve math problems on screen, making interactive learning less engaging and inaccessible for touchless environments.

---

## The Solution

AI Air Canvas uses computer vision and hand tracking to detect specific gestures from a live webcam feed. Users can draw freely in the air using a pinch gesture, erase with a palm gesture, change brush sizes, pick colors, and trigger an AI-powered math solver just by holding a "V" sign making learning interactive, fun, and completely hands-free.

---

## Technical Details

### Technologies/Components Used

**Languages used:**

- Python

**Frameworks used:**

- OpenCV

**Libraries used:**

- MediaPipe (hand landmark detection)
- NumPy
- Google Gemini API / AI Solver integration
- smtplib (automated email delivery of solutions)

**Tools used:**

- VS Code
- Git
- Webcam / Camera input

---

## Features

- **✋ Gesture-Based Drawing:** Use a pinch gesture to draw freely on a virtual canvas overlaid on your live camera feed.
- **🧹 Air Eraser:** Open your palm to instantly erase parts of your drawing — no button clicks needed.
- **🧮 AI Math Solver:** Hold up a "V" sign to trigger the AI solver, which reads your handwritten equation and displays the verified solution in real time (e.g., `7x - 14 = 0 → x = 2`).
- **🎨 Color Palette & Brush Size:** Choose from 9 colors via the top palette bar, and adjust brush size using right-side gestures for precise or bold strokes.
- **📧 Auto Email Solution:** Once the AI solves the equation, the verified result is automatically sent to the user's registered email ID — so you never lose your solutions.

---

## Implementation

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ai-air-canvas.git
cd ai-air-canvas

# Install required dependencies
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

> Make sure your webcam is connected and accessible before running the application.

---

## Project Documentation

### Screenshots

![Screenshot1](screenshots/drawing_mode.png)
_Drawing mode — User writing the equation `7x - 14 = 0` in the air using pinch gesture with red color selected._

![Screenshot2](screenshots/solve_gesture.png)
_Solve gesture detected — "V" hand sign triggers AI solver; result `x = 2` displayed at the bottom of the screen._

![Screenshot3](screenshots/color_palette.png)
_Color palette at the top of the screen with 9 color options; gesture controls overlay shown in the top-left corner._

---

### Diagrams

#### System Architecture

The application captures live video frames from the webcam using OpenCV. Each frame is passed to MediaPipe's hand tracking module, which identifies 21 hand landmarks in real time. Based on the relative positions of key landmarks (index finger tip, thumb tip, etc.), the system classifies the current gesture — pinch (draw), palm (erase), V-sign (solve), or right-side movement (resize brush). Drawing strokes are overlaid directly onto the video frame using NumPy canvas layers. When the solve gesture is detected, the canvas content is sent to the integrated AI model (Gemini API), which interprets the handwritten equation and returns a verified solution, displayed at the bottom of the screen. Simultaneously, the solution is automatically dispatched to the user's registered email ID via smtplib, as seen by the "Sending..." status in the UI.

#### Application Workflow

```
Webcam Input
     ↓
OpenCV Frame Capture
     ↓
MediaPipe Hand Landmark Detection
     ↓
Gesture Classification
  ├── Pinch → Draw on Canvas
  ├── Palm → Erase Canvas
  ├── Hold V → Send to AI Solver → Display Solution → 📧 Email Solution to User
  └── R-Side → Adjust Brush Size
     ↓
Overlay Canvas on Live Video Feed
     ↓
Display Output to User
```

---

## Team Contributions

| Member              | Contribution                                                      |
| ------------------- | ----------------------------------------------------------------- |
| Nivedhya Unnikannan | Hand gesture detection, MediaPipe integration, canvas rendering   |
| Amina K A           | AI solver integration, UI overlay, color palette & brush controls |

---

_Made with ❤️ at Tink-her-hack 4.0 by Team Innovature_
