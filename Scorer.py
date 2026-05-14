from Metrics import MetricsSnapshot
"""

Weights:
  PERCLOS       : 40%  (most reliable, NHTSA standard)
  Head Pose     : 25%  (direct sign of losing consciousness)
  Blink Pattern : 20%  (detects the "fighting sleep" phase)
  Yawn          : 15%  (early warning, less reliable)
 
Usage:
  from scorer import compute_fatigue_score
  score = compute_fatigue_score(snapshot)
"""

#--------------------------
# NORMALIZATION TRESHOLDS 
#--------------------------

PERCLOS_MIN=0.15
PERCLOS_MAX=0.45

PITCH_MIN=15.0
PITCH_MAX=40.0

BLINK_RATE_NORMAL_LOW = 15.0
BLINK_RATE_NORMAL_HIGH = 20.0
BLINK_RATE_DANGER_LOW = 10.0
BLINK_RATE_DANGER_HIGH = 25.0

BLINK_DUR_MIN = 300.0
BLINK_DUR_MAX = 500.0 


YAWN_MAX=4

WEIGHT_PERCLOS = 0.40
WEIGHT_HEAD = 0.25
WEIGHT_BLINK = 0.20
WEIGHT_YAWN = 0.15

PERCLOS_EMERGENCY=0.50
PITCH_EMERGENCY=40.0


def _normalize(value, low, high):
    if value <= low:
        return 0.0
    elif value >= high:
        return 100.0
    return ((value - low) / (high - low)) * 100



def _normalize_blink_rate(rate):
    """
    Blink rate is abnormal in BOTH directions:
    - Too high (> 25/min) = fighting sleep
    - Too low  (< 10/min) = losing the fight
 
    Normal range is 15-20/min.
    """
    if BLINK_RATE_NORMAL_LOW <= rate <= BLINK_RATE_NORMAL_HIGH:
        return 0.0
    if rate > BLINK_RATE_NORMAL_HIGH:
        return _normalize(rate, BLINK_RATE_NORMAL_HIGH, BLINK_RATE_DANGER_HIGH)
    if rate <= BLINK_RATE_DANGER_LOW:
        return 100.0
    return ((BLINK_RATE_NORMAL_LOW - rate)
            / (BLINK_RATE_NORMAL_LOW - BLINK_RATE_DANGER_LOW)) * 100.0
    
def compute_fatigue_score(snapshot: MetricsSnapshot) -> float:
    """
    Compute the global fatigue score (0-100) from a MetricsSnapshot.
 
    This is a pure function with no side effects.
 
    Args:
        snapshot: MetricsSnapshot from FatigueMetrics.update()
 
    Returns:
        float: fatigue score between 0.0 and 100.0
    """
    
    score_perclos = _normalize(snapshot.perclos, PERCLOS_MIN, PERCLOS_MAX)
    score_head= _normalize(abs(snapshot.pitch), PITCH_MIN, PITCH_MAX)
    score_blink_rate = _normalize_blink_rate(snapshot.blink_rate)
    score_blink_dur = _normalize(snapshot.blink_duration, BLINK_DUR_MIN, BLINK_DUR_MAX)
    score_blink = (score_blink_rate + score_blink_dur) / 2.0
    score_yawn = _normalize(snapshot.yawn_count, 0, YAWN_MAX) 
    score = (
        score_perclos * WEIGHT_PERCLOS
        + score_head * WEIGHT_HEAD
        + score_blink * WEIGHT_BLINK
        + score_yawn * WEIGHT_YAWN
    )
    
    
    score = max(0.0, min(100.0, score))
    return score



def check_emergency(snapshot: MetricsSnapshot) -> bool:
    """
    Check if emergency conditions are met for direct escalation to level 3.
 
    These conditions bypass the normal score-based escalation:
    - PERCLOS > 0.50 (eyes closed more than half the time)
    - Pitch > 40 degrees (head fully dropped)
 
    Args:
        snapshot: MetricsSnapshot
 
    Returns:
        bool: True if emergency escalation should happen
    """
    if snapshot.perclos > PERCLOS_EMERGENCY:
        return True
    if abs(snapshot.pitch) > PITCH_EMERGENCY:
        return True
    return False


    
  