# Sentinel — Architecture

## Project Overview

Sentinel is a real-time driver fatigue detection system. It monitors the driver through a camera, computes fatigue metrics from facial landmarks, and alerts the driver with escalating audio alarms before a dangerous event occurs.

---

## Module Structure

```
sentinel/
├── orchestration.py          # Webcam loop, MediaPipe orchestration, entry point
├── calibration.py   # 5s startup calibration to personalize EAR threshold
├── metrics.py       # Stateful tracker: EAR, PERCLOS, blink, head pose, yawn
├── scorer.py        # Pure function: MetricsSnapshot → fatigue score (0-100)
├── alert.py         # 5-level state machine + sound output
└── overlay.py       # Pure function: draws metrics panel onto frame
```

---

## Detection Mode

MediaPipe runs in `LIVE_STREAM` mode (asynchronous).

- `landmarker.detect_async(mp_image, timestamp_ms)` is called each frame — non-blocking
- Results arrive via `result_callback()` on a separate thread
- `MetricsTracker` uses a `threading.Lock` to protect shared state between the callback thread (writer) and the main thread (reader)

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STARTUP                                                         │
│  CalibrationRoutine (5s) → EAR threshold → MetricsTracker       │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ MAIN THREAD (per frame)                                         │
│                                                                 │
│  cv2.VideoCapture                                               │
│      │                                                          │
│      ▼                                                          │
│  flip + BGR→RGB + wrap mp.Image                                 │
│      │                                                          │
│      ▼                                                          │
│  landmarker.detect_async(mp_image, timestamp_ms)  ───────────── ┼──┐
│      │                                                          │  │
│      ▼                                                          │  │
│  snapshot = metrics_tracker.get_snapshot()  ◄──── (Lock read)   │  │
│      │                                                          │  │
│      ▼                                                          │  │
│  score = compute_score(snapshot)                                │  │
│      │                                                          │  │
│      ▼                                                          │  │
│  alert_level = alert_state_machine.update(score)                │  │
│      │                                                          │  │
│      ▼                                                          │  │
│  frame = draw(frame, snapshot, score, alert_level)              │  │
│      │                                                          │  │
│      ▼                                                          │  │
│  cv2.imshow                                                     │  │
└─────────────────────────────────────────────────────────────────┘  │
                                                                     │
┌─────────────────────────────────────────────────────────────────┐  │
│ CALLBACK THREAD (per detection result)                          │◄─┘
│                                                                 │
│  result_callback(result, image, timestamp_ms)                   │
│      │                                                          │
│      ├── extract 478 landmarks                                  │
│      │                                                          │
│      ├── metrics_tracker.update(landmarks, timestamp_ms)        │
│      │       │  (Lock write)                                    │
│      │       ├── compute EAR → PERCLOS window, blink events     │
│      │       ├── compute MAR → yawn events                      │
│      │       └── solvePnP → pitch, yaw, roll                    │
│      │                                                          │
│      └── snapshot stored internally                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Data Contract

`MetricsSnapshot` is the single object passed between all modules. No module downstream of `metrics.py` touches raw landmarks.

```python
@dataclass
class MetricsSnapshot:
    ear: float               # raw EAR, both eyes averaged
    perclos: float           # 0.0 - 1.0 over 30s sliding window
    blink_rate: float        # blinks per minute
    blink_duration_ms: float # rolling average of last 10 blinks (ms)
    pitch: float             # degrees — primary fatigue indicator
    yaw: float               # degrees
    roll: float              # degrees
    yawn_count: int          # confirmed yawns in last 5 minutes
    is_calibrated: bool      # False during startup calibration
```

---

## Module Responsibilities

### `calibration.py`
- Captures 5 seconds of frames with eyes open at startup
- Computes mean EAR over the window
- Sets personalized closure threshold: `threshold = mean_ear * 0.75`
- Returns a `CalibrationResult` consumed by `MetricsTracker`

### `metrics.py` — `MetricsTracker`
Stateful class, thread-safe via `threading.Lock`.

**EAR (Eye Aspect Ratio)**
- Formula: `EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)`
- Right eye landmarks: 33, 160, 158, 133, 153, 144
- Left eye landmarks: 362, 385, 387, 263, 373, 380
- Threshold: `EAR < calibrated_threshold` → eye closed

**PERCLOS** (from EAR)
- 30-second sliding window of frames
- `PERCLOS = closed_frames / total_frames`

**Blink Rate** (from EAR)
- Blink: EAR drops below threshold and recovers within 100–500ms
- Count per minute via rolling timestamp buffer

**Blink Duration** (from EAR)
- Duration: `timestamp_eye_open - timestamp_eye_closed`
- Rolling average of last 10 blinks
- Events > 500ms are not blinks — counted as PERCLOS, not blink duration

**Head Pose** (solvePnP)
- 6 reference landmarks:

| Point              | MediaPipe index|
|------------------- |----------------|
| Nose tip           | 1              |
| Chin               | 152            |
| Left eye corner    | 263            |
| Right eye corner   | 33             |
| Left mouth corner  | 291.           |
| Right mouth corner | 61             |

- `cv2.solvePnP` → rotation vector → `cv2.Rodrigues` → Euler angles (pitch, yaw, roll)
- Pitch is the primary fatigue indicator (head drooping forward)
- Angle must exceed threshold for > 2s consecutively to register

**MAR / Yawn** (Mouth Aspect Ratio)
- Formula: `MAR = (||p2-p8|| + ||p3-p7|| + ||p4-p6||) / (2 * ||p1-p5||)`
- Landmarks: 61 (left corner), 291 (right corner), 13, 0 (upper lip), 17, 14 (lower lip)
- Yawn confirmed: `MAR > 0.6` sustained for > 2s
- Counter: yawns in last 5-minute rolling window

---

### `scorer.py` — `compute_score(snapshot) -> float`

Pure function, no state.

**Formula:**
```
SCORE = (Score_PERCLOS × 0.40) + (Score_HeadPose × 0.25) + (Score_BlinkPattern × 0.20) + (Score_Yawn × 0.15)
```

**Normalization (each metric → 0–100):**

```
Score_PERCLOS:
  PERCLOS < 0.15        → 0
  PERCLOS > 0.45        → 100
  else                  → (PERCLOS - 0.15) / 0.30 × 100

Score_HeadPose (pitch-primary):
  pitch < 15°           → 0
  pitch > 40°           → 100
  else                  → (pitch - 15) / 25 × 100

Score_BlinkRate:
  15 ≤ rate ≤ 20        → 0
  rate > 25 or < 10     → 100
  else                  → linear interpolation

Score_BlinkDuration:
  duration < 300ms      → 0
  duration > 500ms      → 100
  else                  → (duration - 300) / 200 × 100

Score_BlinkPattern = (Score_BlinkRate + Score_BlinkDuration) / 2

Score_Yawn:
  0 yawns               → 0
  1 yawn                → 25
  2 yawns               → 50
  3 yawns               → 75
  4+ yawns              → 100
```

**Hard escalation rules (bypass score):**
- `PERCLOS > 0.50` → force Level 3
- `pitch > 40°` sustained for > 3s → force Level 3

---

### `alert.py` — `AlertStateMachine`

**5 alert levels:**

| Level     | Score | Action                        |
|-------    |-------|-------------------------------|
| 0         | 0–29  | Silent monitoring             |
| 1         | 30–54 | Short beep every 3s           |
| 2         | 55–74 | Continuous alarm              |
| 3         | 75–89 | Voice message + 10s countdown |
| 4         | 90–100| emergency stop.               |

**Escalation:** immediate when score crosses threshold upward.

**De-escalation (deliberately slow to prevent oscillation):**
```
Level 3 → 2 : score < 75 for 5s consecutive
Level 2 → 1 : score < 55 for 5s consecutive
Level 1 → 0 : score < 30 for 10s consecutive
Level 4     : no automatic return
```

**Post-alert cooldown:** after returning to Level 0, thresholds are lowered by 10% for 5 minutes.

**Sound:** `pygame.mixer` (cross-platform). Generates beep tones programmatically — no external audio files required.

---

### `overlay.py` — `draw(frame, snapshot, score, level) -> frame`

Pure function. Draws a metrics panel on the right side of the frame:

```
┌────────────────────────────────────────┐
│  SENTINEL                    [LEVEL 1] │
│                                        │
│  EAR       0.24                        │
│  PERCLOS   ████░░░░░░  18%             │
│  Blink     16/min  |  240ms            │
│  Pitch     12°  Yaw 5°  Roll 2°        │
│  Yawns     1 in 5min                   │
│                                        │
│  FATIGUE SCORE                         │
│  ████████░░░░░░░░░░░░  38 / 100        │
└────────────────────────────────────────┘
```

Alert level badge changes color:
- Level 0: green
- Level 1: yellow
- Level 2: orange
- Level 3: red
- Level 4: flashing red

---

## Startup Sequence

```
1. Open webcam
2. Run calibration (5s) — display "Look at the camera" prompt
3. Receive EAR threshold from calibration
4. Initialize MetricsTracker with threshold
5. Initialize AlertStateMachine
6. Enter main detection loop
```

---

## Dependencies

```
mediapipe
opencv-python
pygame       # cross-platform audio
numpy
```
