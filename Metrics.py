import time , math 
from collections import deque
from dataclasses import dataclass 
import numpy as np 
import cv2 


@dataclass 
class MetricsSnapshot:
     
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

# INDEXES OF THE FACIAL LANDMARKS USED FOR METRICS CALCULATION
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
LEFT_EYE = [362, 385, 387, 263, 373, 380]

# Mouth landmarks for MAR
UPPER_LIP = 13
LOWER_LIP = 14
LEFT_MOUTH = 61
RIGHT_MOUTH = 291
UPPER_LIP_TOP = 0
LOWER_LIP_BOTTOM = 17

#HEAD pose Landmarks 
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
        vertical_2=_distance(points[2]-points[4]) #||p3-p5|| 
        horizontal=_distance(points[0],points[3]) #||p1-p4||
        if horizontal < 1e-6 :
            return 0.0 
        return (vertical_1 + vertical_2) / (2.0 * horizontal)       
        
    left_ear=_ear_for_eye(LEFT_EYE)
    right_ear=_ear_for_eye(RIGHT_EYE)
    return left_ear, right_ear

def compute_head_poss(landmarks,w,h):
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
    
    
    
    
    