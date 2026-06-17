import cv2
import numpy as np
import time
import math
import threading
from collections import deque
import tensorflow as tf


import paho.mqtt.client as mqtt
import json
import time
import base64
import datetime
import subprocess



client = mqtt.Client()
client.connect("broker.hivemq.com", 1883, 60)
client.loop_start()

# ==================================================
# RTSP CAMERAS
# ==================================================

RTSP_URLS = [

    "rtsp://pulkitgarg:pulkitgarg@192.168.247.32:554/stream1",

    "rtsp://pulkitgargtce:pulkitgargtce@192.168.255.233:554/stream2",

    # Add more cameras here
]

MODEL_PATH = "movenet_singlepose_thunder.tflite"

interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

print("Input Shape:", input_details[0]['shape'])

# ==========================
# KEYPOINT CONNECTIONS
# ==========================

EDGES = [
    (0,1),(0,2),
    (1,3),(2,4),
    (0,5),(0,6),
    (5,7),(7,9),
    (6,8),(8,10),
    (5,6),
    (5,11),(6,12),
    (11,12),
    (11,13),(13,15),
    (12,14),(14,16)
]

# ==========================
# POSE ESTIMATION
# ==========================

def detect_pose(frame):

    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    input_img = cv2.resize(img, (192, 192))

    input_img = np.expand_dims(input_img, axis=0)
    input_img = input_img.astype(np.uint8)

    interpreter.set_tensor(
        input_details[0]['index'],
        input_img
    )

    interpreter.invoke()

    keypoints = interpreter.get_tensor(
        output_details[0]['index']
    )

    return keypoints[0][0]

# ==========================
# POSTURE CLASSIFICATION
# ==========================

def classify_posture(keypoints, threshold=0.3):

    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6

    LEFT_HIP = 11
    RIGHT_HIP = 12

    LEFT_KNEE = 13
    RIGHT_KNEE = 14

    required = [
        LEFT_SHOULDER,
        RIGHT_SHOULDER,
        LEFT_HIP,
        RIGHT_HIP,
        LEFT_KNEE,
        RIGHT_KNEE
    ]

    for idx in required:
        if keypoints[idx][2] < threshold:
            return "UNKNOWN"

    # Centers
    shoulder_x = (
        keypoints[LEFT_SHOULDER][1] +
        keypoints[RIGHT_SHOULDER][1]
    ) / 2

    shoulder_y = (
        keypoints[LEFT_SHOULDER][0] +
        keypoints[RIGHT_SHOULDER][0]
    ) / 2

    hip_x = (
        keypoints[LEFT_HIP][1] +
        keypoints[RIGHT_HIP][1]
    ) / 2

    hip_y = (
        keypoints[LEFT_HIP][0] +
        keypoints[RIGHT_HIP][0]
    ) / 2

    dx = shoulder_x - hip_x
    dy = shoulder_y - hip_y

    torso_angle = abs(
        math.degrees(
            math.atan2(dy, dx)
        )
    )

    knee_y = (
        keypoints[LEFT_KNEE][0] +
        keypoints[RIGHT_KNEE][0]
    ) / 2

    hip_to_knee = abs(knee_y - hip_y)

    # Classification

    if torso_angle < 35:
        posture = "LYING"

    elif hip_to_knee < 0.12:
        posture = "SITTING"

    else:
        posture = "STANDING"

    return posture

# ==========================
# DRAW SKELETON
# ==========================

def draw_pose(frame, keypoints, threshold=0.3):

    h, w, _ = frame.shape

    points = []

    for kp in keypoints:

        y, x, conf = kp

        px = int(x * w)
        py = int(y * h)

        points.append((px, py, conf))

        if conf > threshold:
            cv2.circle(
                frame,
                (px, py),
                5,
                (0,255,0),
                -1
            )

    for p1, p2 in EDGES:

        if (
            points[p1][2] > threshold and
            points[p2][2] > threshold
        ):

            cv2.line(
                frame,
                (points[p1][0], points[p1][1]),
                (points[p2][0], points[p2][1]),
                (255,0,0),
                2
            )




def send_mqtt_alert(cam_id, event, frame=None):

    payload = {
        "camera": cam_id,
        "event": event,
        "time": time.time()
    }

    if frame is not None:

        # Reduce image size
        small = cv2.resize(frame, (320, 180))

        # Compress JPEG
        _, buffer = cv2.imencode(
            ".jpg",
            small,
            [cv2.IMWRITE_JPEG_QUALITY, 60]
        )

        image_b64 = base64.b64encode(
            buffer
        ).decode("utf-8")

        payload["image"] = image_b64

    client.publish(
        "eldercare/alert",
        json.dumps(payload)
    )

    print(
        f"MQTT SENT: CAM {cam_id} {event}"
    )

# ==================================================
# OPEN CAMERAS
# ==================================================

caps = []

for url in RTSP_URLS:

    cap = cv2.VideoCapture(url)

    if not cap.isOpened():
        print("Cannot open:", url)
        exit()

    caps.append(cap)

# ==================================================
# CAMERA STATES
# ==================================================

camera_states = []

for _ in RTSP_URLS:

    camera_states.append({

        "prev_nose_y": None,

        "rapid_drop": False,

        "lying_start": None,

        "fall_detected": False,

        "posture_history": deque(maxlen=20),

        "sit_triggered": False,

        "last_seen": "Never"
    })

# ==================================================
# ALARM
# ==================================================

alarm_running = False

def ring_alarm():

    global alarm_running

    if alarm_running:
        return

    alarm_running = True

    try:

        proc = subprocess.Popen(
            [
                "cvlc",
                "--play-and-exit",
                "Alarm01.wav"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        proc.wait()

    finally:
        alarm_running = False

prev_time = time.time()

# ==================================================
# MAIN LOOP
# ==================================================

while True:

    frames = []

    current_time = time.time()

    for cam_index, cap in enumerate(caps):

        ret, frame = cap.read()

        if not ret:

            frame = np.zeros(
                (360,640,3),
                dtype=np.uint8
            )

            cv2.putText(
                frame,
                f"CAM {cam_index+1} OFFLINE",
                (100,180),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0,0,255),
                3
            )

            frames.append(frame)

            continue
        
        frame = cv2.resize(frame, (640, 360))

        keypoints = detect_pose(frame)

        state = camera_states[cam_index]

        if keypoints is not None:

            draw_pose(frame, keypoints)

            stable_posture = classify_posture(keypoints)
            

            # =====================================
            # TEMPORAL SMOOTHING
            # =====================================

            current_posture = classify_posture(keypoints)

            state["posture_history"].append(current_posture)

            if state["posture_history"]:

                stable_posture = max(
                    set(state["posture_history"]),
                    key=state["posture_history"].count
                )

            else:

                stable_posture = "UNKNOWN"


            # =====================================
            # NOSE TRACKING
            # =====================================

            nose_y = keypoints[0][0]

            rapid_drop = False

            if state["prev_nose_y"] is not None:

                delta_y = (
                    nose_y -
                    state["prev_nose_y"]
                )

                if delta_y > 0.08:

                    rapid_drop = True

            state["prev_nose_y"] = nose_y

            if rapid_drop:
                state["rapid_drop"] = True

            # =====================================
            # FALL DETECTION
            # =====================================

            if stable_posture == "LYING":

                if state["lying_start"] is None:

                    state["lying_start"] = \
                        current_time

                lying_duration = \
                    current_time - \
                    state["lying_start"]

                if (
                    lying_duration > 2
                    and
                    state["rapid_drop"]
                ):

                    state["fall_detected"] = True

            else:

                state["lying_start"] = None

                if stable_posture == "STANDING":

                    state["rapid_drop"] = False

                    state["fall_detected"] = False

            # =====================================
            # SITTING ALARM
            # =====================================

            if stable_posture == "SITTING":

                if not state["sit_triggered"]:

                    state["sit_triggered"] = True

                    # send MQTT + snapshot once
                    send_mqtt_alert(
                        cam_index,
                        "SITTING",
                        frame
                    )

                    threading.Thread(
                        target=ring_alarm,
                        daemon=True
                    ).start()

            else:

                state["sit_triggered"] = False

            # =====================================
            # DISPLAY
            # =====================================

            
            cv2.putText(
                frame,
                f"POSTURE: {stable_posture}",
                (20,70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0,255,255),
                2
            )
     
            if state["fall_detected"]:

                cv2.putText(
                    frame,
                    "FALL DETECTED",
                    (20,280),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0,0,255),
                    3
                )
        
        cv2.putText(
                frame,
                f"CAM {cam_index+1}",
                (20,280),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255,255,0),
                2
            )

        cv2.putText(
                frame,
                f"LAST SEEN: {state['last_seen']}",
                (20,310),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255,255,0),
                2
            )


        frames.append(frame)

        
    # =====================================
    # FPS
    # =====================================

    fps = 1 / (time.time() - prev_time)

    prev_time = time.time()

    # =====================================
    # COMBINE DISPLAY
    # =====================================

    if len(frames) == 1:

        combined = frames[0]

    elif len(frames) == 2:

        combined = np.hstack(frames)

    else:

        rows = []

        for i in range(0, len(frames), 2):

            if i + 1 < len(frames):

                row = np.hstack(
                    [frames[i], frames[i+1]]
                )

            else:

                blank = np.zeros_like(frames[i])

                row = np.hstack(
                    [frames[i], blank]
                )

            rows.append(row)

        combined = np.vstack(rows)
       

    cv2.imshow(
        "Multi Camera Fall Detection",
        combined
    )

    if cv2.waitKey(1) & 0xFF == 27:
        break

# ==================================================
# CLEANUP
# ==================================================

for cap in caps:
    cap.release()

cv2.destroyAllWindows()