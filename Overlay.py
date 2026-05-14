"""
Pure function that draws the metrics panel onto an OpenCV frame.
 
No state, no side effects. Takes a frame + metrics + level,
draws everything, returns the modified frame.
 
The overlay shows:
  - Top bar: SENTINEL logo, status, FPS
  - Right panel: EAR, PERCLOS, Head Pose, MAR gauges
  - Score bar: colored fatigue score (green -> red)
  - Alert level indicator with flashing on danger
  - Bottom bar: current alert action description

    """
    
    
import time
import cv2
import numpy as np
 
from Metrics import MetricsSnapshot
 
 
# ============================================================
# COLORS (BGR)
# ============================================================
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_BG = (30, 30, 30)
GREEN = (0, 200, 0)
YELLOW = (0, 220, 220)
ORANGE = (0, 140, 255)
RED = (0, 0, 255)
CYAN = (255, 255, 0)
GRAY = (150, 150, 150)
 
# Level colors
LEVEL_COLORS = {
    0: GREEN,
    1: YELLOW,
    2: ORANGE,
    3: RED,
    4: (0, 0, 200),  # dark red
}
 
# Level labels
LEVEL_LABELS = {
    0: "NORMAL",
    1: "SOMNOLENT",
    2: "DANGEREUX",
    3: "CRITIQUE",
    4: "ARRET D'URGENCE",
}
 
# Level action descriptions
LEVEL_ACTIONS = {
    0: "Monitoring passif",
    1: "Alerte sonore legere",
    2: "Alarme forte + vibration",
    3: "Reprenez le controle ! Countdown...",
    4: "Sequence d'arret d'urgence en cours",
}
 
 
# ============================================================
# MAIN OVERLAY FUNCTION
# ============================================================
 
def draw_overlay(frame, snapshot, score, level, fps):
    """
    Draw the complete metrics overlay onto the frame.
 
    Args:
        frame:    numpy array (BGR image from OpenCV)
        snapshot: MetricsSnapshot from metrics.py (or None if no face)
        score:    float 0-100 fatigue score (or 0 if no face)
        level:    int 0-4 alert level
        fps:      float current FPS
 
    Returns:
        numpy array: the frame with overlay drawn
    """
    h, w = frame.shape[:2]
 
    _draw_top_bar(frame, w, snapshot is not None, fps)
 
    if snapshot is not None:
        _draw_metrics_panel(frame, w, h, snapshot)
        _draw_score_bar(frame, w, h, score)
 
    _draw_level_indicator(frame, w, h, level)
    _draw_bottom_bar(frame, w, h, level)
 
    return frame
 
 
# ============================================================
# COMPONENT DRAWING FUNCTIONS
# ============================================================
 
def _draw_top_bar(frame, w, face_detected, fps):
    """Top bar with logo, face status, and FPS."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 45), DARK_BG, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
 
    # Logo
    cv2.putText(frame, "SENTINEL", (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, WHITE, 2)
 
    # Face status
    if face_detected:
        status = "VISAGE DETECTE"
        color = GREEN
    else:
        status = "AUCUN VISAGE"
        color = RED
    cv2.putText(frame, status, (180, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
 
    # FPS
    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 90, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, GRAY, 1)
 
 
def _draw_metrics_panel(frame, w, h, snapshot):
    """Right-side panel showing all metric values."""
    panel_w = 200
    panel_x = w - panel_w - 10
    panel_y = 55
 
    # Semi-transparent background
    overlay = frame.copy()
    cv2.rectangle(overlay, (panel_x - 5, panel_y),
                  (w - 5, panel_y + 230), DARK_BG, -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
 
    y = panel_y + 20
    line_h = 28
 
    metrics = [
        ("EAR", f"{snapshot.ear:.3f}", _ear_color(snapshot.ear)),
        ("PERCLOS", f"{snapshot.perclos:.1%}", _perclos_color(snapshot.perclos)),
        ("Blink/min", f"{snapshot.blink_rate:.0f}", _blink_color(snapshot.blink_rate)),
        ("Blink ms", f"{snapshot.blink_duration:.0f}", _duration_color(snapshot.blink_duration)),
        ("Pitch", f"{snapshot.pitch:.1f} deg", _pitch_color(snapshot.pitch)),
        ("Yaw", f"{snapshot.yaw:.1f} deg", WHITE),
        ("MAR", f"{snapshot.mar:.3f}", _mar_color(snapshot.mar)),
        ("Yawns", f"{snapshot.yawn_count}", _yawn_color(snapshot.yawn_count)),
    ]
 
    for label, value, color in metrics:
        cv2.putText(frame, label, (panel_x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, GRAY, 1)
        cv2.putText(frame, value, (panel_x + 100, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        y += line_h
 
 
def _draw_score_bar(frame, w, h, score):
    """Horizontal score bar at the bottom of the metrics panel."""
    bar_x = w - 210
    bar_y = h - 80
    bar_w = 195
    bar_h = 20
 
    # Background
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                  (50, 50, 50), -1)
 
    # Filled portion
    fill_w = int(bar_w * (score / 100.0))
    color = _score_color(score)
    if fill_w > 0:
        cv2.rectangle(frame, (bar_x, bar_y),
                      (bar_x + fill_w, bar_y + bar_h), color, -1)
 
    # Border
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                  WHITE, 1)
 
    # Score text
    cv2.putText(frame, f"Score: {score:.0f}/100", (bar_x, bar_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
 
 
def _draw_level_indicator(frame, w, h, level):
    """Large level indicator on the left side."""
    color = LEVEL_COLORS.get(level, WHITE)
    label = LEVEL_LABELS.get(level, "?")
 
    # Flash effect for levels 3 and 4
    if level >= 3 and int(time.time() * 4) % 2 == 0:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 80), -1)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
 
    # Level badge
    badge_x = 12
    badge_y = h - 80
    badge_w = 180
    badge_h = 50
 
    cv2.rectangle(frame, (badge_x, badge_y),
                  (badge_x + badge_w, badge_y + badge_h), color, -1)
    cv2.rectangle(frame, (badge_x, badge_y),
                  (badge_x + badge_w, badge_y + badge_h), WHITE, 1)
 
    cv2.putText(frame, f"Nv.{level}", (badge_x + 8, badge_y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, BLACK, 2)
    cv2.putText(frame, label, (badge_x + 8, badge_y + 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, BLACK, 1)
 
 
def _draw_bottom_bar(frame, w, h, level):
    """Bottom bar showing current action description."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 28), (w, h), DARK_BG, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
 
    action = LEVEL_ACTIONS.get(level, "")
    color = LEVEL_COLORS.get(level, WHITE)
    cv2.putText(frame, action, (12, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
 
    cv2.putText(frame, "Q: Quitter", (w - 100, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, GRAY, 1)
 
 
# ============================================================
# COLOR HELPERS
# ============================================================
 
def _score_color(score):
    """Green at 0, yellow at 50, red at 100."""
    if score < 30:
        return GREEN
    elif score < 55:
        return YELLOW
    elif score < 75:
        return ORANGE
    else:
        return RED
 
 
def _ear_color(ear):
    if ear > 0.25:
        return GREEN
    elif ear > 0.18:
        return YELLOW
    else:
        return RED
 
 
def _perclos_color(perclos):
    if perclos < 0.15:
        return GREEN
    elif perclos < 0.30:
        return YELLOW
    elif perclos < 0.45:
        return ORANGE
    else:
        return RED
 
 
def _blink_color(rate):
    if 15 <= rate <= 20:
        return GREEN
    elif 10 <= rate <= 25:
        return YELLOW
    else:
        return RED
 
 
def _duration_color(duration):
    if duration < 300:
        return GREEN
    elif duration < 500:
        return YELLOW
    else:
        return RED
 
 
def _pitch_color(pitch):
    if abs(pitch) < 15:
        return GREEN
    elif abs(pitch) < 25:
        return YELLOW
    else:
        return RED
 
 
def _mar_color(mar):
    if mar < 0.5:
        return GREEN
    elif mar < 0.6:
        return YELLOW
    else:
        return RED
 
 
def _yawn_color(count):
    if count <= 1:
        return GREEN
    elif count <= 3:
        return YELLOW
    else:
        return RED