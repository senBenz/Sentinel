import time , math 
from collections import deque
from dataclasses import dataclass 
import numpy as np 
import cv2 


@dataclass 
class MetricsSnapshot:
    """Immutable snapshot of all fatigue metrics at a given moment .
    """
     
    ear : float
    perclos : float 
    blink_rate : float
    blink_duration : float 
    pitch:float
    yaw:float
    roll : float 
    mar :float 
    yawn_count : int
    eyes_closed : bool
    timestamp : float

RIGHT_EYE = [33, 160, 158, 133, 153, 144]
LEFT_EYE = [362, 385, 387, 263, 373, 380]


UPPER_LIP = 13
LOWER_LIP = 14
LEFT_MOUTH = 61
RIGHT_MOUTH = 291
UPPER_LIP_TOP = 0
LOWER_LIP_BOTTOM = 17

NOSE_TIP=1
CHIN=152
LEFT_EYE_CORNER=263
RIGHT_EYE_CORNER=33
LEFT_MOUTH_CORNER=291
RIGHT_MOUTH_CORNER=61

def _distance(p1,p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def compute_ear(landmarks, w, h ): 
    #---------------------------------------------------
    #EAR SECTION : 
    # Formula:
    #  EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    #----------------------------------------------------
    
    def _ear_for_eye(indicies): 
        # CALCULATING a certain ear for a certain eye 
        points= [(landmarks[i].x*w,landmarks[i].y*h)for i in indicies]
        # EYE POINTS FOR EAR : 
        #p1=outer corner,p2=upper outer , p3=upper inner 
        #p4=inner corner , p5=lower inner , p6=lower outer 
        vertical_1=_distance(points[1],points[5]) #||p2-p6||
        vertical_2=_distance(points[2],points[4]) #||p3-p5|| 
        horizontal=_distance(points[0],points[3]) #||p1-p4||
        if horizontal < 1e-6 :
            return 0.0 
        return (vertical_1 + vertical_2) / (2.0 * horizontal)       
        
    left_ear=_ear_for_eye(LEFT_EYE)
    right_ear=_ear_for_eye(RIGHT_EYE)
    return left_ear, right_ear

def compute_mar(landmarks, w, h):
    """
    Compute Mouth Aspect Ratio for yawn detection.
 
    Formula:
      MAR = (||upper-lower|| + ||top-bottom||) / (2 * ||left-right||)
 
    Args:
        landmarks: list of 478 NormalizedLandmark
        w, h: frame dimensions
 
    Returns:
        float: MAR value (higher = mouth more open)
    """
    def _pt(idx):
        return (landmarks[idx].x * w, landmarks[idx].y * h)
 
    upper = _pt(UPPER_LIP)
    lower = _pt(LOWER_LIP)
    top = _pt(UPPER_LIP_TOP)
    bottom = _pt(LOWER_LIP_BOTTOM)
    left = _pt(LEFT_MOUTH)
    right = _pt(RIGHT_MOUTH)
 
    vertical_1 = _distance(upper, lower)
    vertical_2 = _distance(top, bottom)
    horizontal = _distance(left, right)
 
    if horizontal < 1e-6:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)

def compute_head_pose(landmarks,w,h):
    #----------------------------------------------
    #HEAD POSE SECTION :
    # Compute head orientation : pitch, yaw, roll
    #---------------------------------------------- 
    
    model_points= np.array(
        [[0.0, 0.0, 0.0],         # Nose tip
        [0.0, -330.0, -65.0],     # Chin
        [-225.0, 170.0, -135.0],  # Left eye corner
        [225.0, 170.0, -135.0],   # Right eye corner
        [-150.0, -150.0, -125.0], # Left mouth corner
        [150.0, -150.0, -125.0],  # Right mouth corner
    ], dtype=np.float64)
    
    indices=[
        NOSE_TIP,
        CHIN,
        LEFT_EYE_CORNER,
        RIGHT_EYE_CORNER,
        LEFT_MOUTH_CORNER,
        RIGHT_MOUTH_CORNER

    ]
    
    image_points = np.array([
        (landmarks[i].x * w, landmarks[i].y * h) for i in indices
    ], dtype=np.float64)
    
    focal_length = w
    center= (w / 2, h / 2)
    camera_matrix= np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ],dtype=np.float64)
    dist_coeffs=np.zeros((4,1))
    
    success , rotation_vec , translation_vec = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE)
    
    if not success:
        return 0.0, 0.0, 0.0
    
    # Convert rotation vector to rotation matrix, then to Euler angles
    rotation_mat, _ = cv2.Rodrigues(rotation_vec)
    
 
 
    # decomposeProjectionMatrix is unreliable, use manual extraction
    sy = math.sqrt(rotation_mat[0, 0] ** 2 + rotation_mat[1, 0] ** 2)
    if sy > 1e-6:
        pitch = math.degrees(math.atan2(rotation_mat[2, 1], rotation_mat[2, 2]))
        yaw = math.degrees(math.atan2(-rotation_mat[2, 0], sy))
        roll = math.degrees(math.atan2(rotation_mat[1, 0], rotation_mat[0, 0]))
    else:
        pitch = math.degrees(math.atan2(-rotation_mat[1, 2], rotation_mat[1, 1]))
        yaw = math.degrees(math.atan2(-rotation_mat[2, 0], sy))
        roll = 0.0
 
    return pitch, yaw, roll
 
    
    
 
class FatigueMetrics:
    """
    Stateful tracker that maintains sliding windows and counters
    to compute temporal metrics (PERCLOS, blink rate, yawn count).
 
    Call update() once per frame with the latest landmarks.
    It returns a MetricsSnapshot with all current values.
    """
 
    def __init__(self, ear_threshold=0.20):
        self.ear_threshold = ear_threshold
 
        self.perclos_window = 30.0  
        self.eye_states = deque()   
 
        self.blink_timestamps = deque()    
        self.blink_durations = deque(maxlen=10)  
        self.blink_window = 60.0           
        self._eyes_were_closed = False
        self._close_start_time = None
 
       
        self.mar_threshold = 0.6
        self.yawn_min_duration = 2.0       
        self.yawn_window = 300.0           
        self.yawn_timestamps = deque()
        self._mouth_was_open = False
        self._mouth_open_start = None
 
    def update(self, landmarks, w, h):
        """
        Process one frame of landmarks and return updated metrics.
 
        Args:
            landmarks: list of 478 NormalizedLandmark
            w, h: frame dimensions in pixels
 
        Returns:
            MetricsSnapshot with all current values
        """
        now = time.time()
 

        left_ear, right_ear = compute_ear(landmarks, w, h)
        ear = (left_ear + right_ear) / 2.0
        eyes_closed = ear < self.ear_threshold
 
        mar = compute_mar(landmarks, w, h)
        pitch, yaw, roll = compute_head_pose(landmarks, w, h)
 
        
        self.eye_states.append((now, eyes_closed))
        
        
        cutoff = now - self.perclos_window
        while self.eye_states and self.eye_states[0][0] < cutoff:
            self.eye_states.popleft()
 
        if len(self.eye_states) > 0:
            closed_count = sum(1 for _, closed in self.eye_states if closed)
            perclos = closed_count / len(self.eye_states)
        else:
            perclos = 0.0
 
        
        self._update_blinks(eyes_closed, now)
 
        
        blink_cutoff = now - self.blink_window
        while self.blink_timestamps and self.blink_timestamps[0] < blink_cutoff:
            self.blink_timestamps.popleft()
 
        blink_rate = len(self.blink_timestamps)  
        blink_duration = (
            float(np.mean(self.blink_durations))
            if self.blink_durations else 250.0
        )
 
        
        self._update_yawns(mar, now)
 
        yawn_cutoff = now - self.yawn_window
        while self.yawn_timestamps and self.yawn_timestamps[0] < yawn_cutoff:
            self.yawn_timestamps.popleft()
 
        yawn_count = len(self.yawn_timestamps)
 
        return MetricsSnapshot(
            ear=ear,
            perclos=perclos,
            blink_rate=blink_rate,
            blink_duration=blink_duration,
            pitch=pitch,
            yaw=yaw,
            roll=roll,
            mar=mar,
            yawn_count=yawn_count,
            eyes_closed=eyes_closed,
            timestamp=now,
        )
 
    def _update_blinks(self, eyes_closed, now):
        """
        Track blink events.
        A blink = eyes close (EAR drops below threshold) then reopen
        within 500ms. Longer closures are not blinks, they are
        counted by PERCLOS instead.
        """
        if eyes_closed and not self._eyes_were_closed:
            
            self._close_start_time = now
 
        elif not eyes_closed and self._eyes_were_closed:
            
            if self._close_start_time is not None:
                duration_ms = (now - self._close_start_time) * 1000
 
                if 50 < duration_ms < 500:
                    
                    self.blink_timestamps.append(now)
                    self.blink_durations.append(duration_ms)
 
            self._close_start_time = None
 
        self._eyes_were_closed = eyes_closed
 
    def _update_yawns(self, mar, now):
        """
        Track yawn events.
        A yawn = mouth opens wide (MAR > threshold) for > 2 seconds.
        """
        mouth_open = mar > self.mar_threshold
 
        if mouth_open and not self._mouth_was_open:
            
            self._mouth_open_start = now
 
        elif not mouth_open and self._mouth_was_open:
           
            if self._mouth_open_start is not None:
                duration = now - self._mouth_open_start
                if duration >= self.yawn_min_duration:
                    self.yawn_timestamps.append(now)
            self._mouth_open_start = None
 
        self._mouth_was_open = mouth_open