import os

os.environ[
    "OPENCV_FFMPEG_CAPTURE_OPTIONS"
] = "rtsp_transport;tcp|stimeout;5000000"

import cv2
import numpy as np
import time
import math
import threading
from collections import deque
import tensorflow as tf


import paho.mqtt.client as mqtt
import base64
import datetime
import subprocess
import requests
import tempfile

from datetime import datetime
import json


client = mqtt.Client()
try:
    client.connect("broker.hivemq.com", 1883, 60)
    client.loop_start()
except Exception as e:
    print("MQTT connection failed:", e)
    

TELEGRAM_TARGETS = [
    {
        "token": "7848156622:AAGRAeQBLbI-oYeriVrg-Atw-D4sliAnfVc",
        "chat_id": "8534377611"
    },
    {
        "token": "8657720952:AAElWv27nt6wsQTdHkCLMK9p1iejzQtJ8_c",
        "chat_id": "8109125975"
    },
    {
        "token": "BOT_TOKEN_3",
        "chat_id": "CHAT_ID_3"
    }
]

# TOKEN = "7848156622:AAGRAeQBLbI-oYeriVrg-Atw-D4sliAnfVc"
# CHAT_ID = "8534377611"

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


camera_frames = [None] * len(RTSP_URLS)

camera_online = [False] * len(RTSP_URLS)

camera_last_frame_time = [
    0
] * len(RTSP_URLS)


frame_locks = [
    threading.Lock()
    for _ in RTSP_URLS
]


def camera_worker(cam_index):

    while True:

        cap = None

        try:

            print(
                f"[CAM {cam_index+1}] Connecting..."
            )

            cap = cv2.VideoCapture(
                RTSP_URLS[cam_index]
            )

            if not cap.isOpened():

                print(
                    f"[CAM {cam_index+1}] Offline"
                )

                time.sleep(5)
                continue

            print(
                f"[CAM {cam_index+1}] Connected"
            )

            camera_online[cam_index] = True

            while True:

                ret, frame = cap.read()

                if not ret:

                    print(
                        f"[CAM {cam_index+1}] Lost"
                    )

                    camera_online[cam_index] = False

                    with frame_locks[cam_index]:
                        camera_frames[cam_index] = None

                    break

                with frame_locks[cam_index]:
                    camera_frames[cam_index] = frame.copy()

                camera_last_frame_time[cam_index] = time.time()
                camera_online[cam_index] = True

        except Exception as e:

            print(
                f"[CAM {cam_index+1}] {e}"
            )

        camera_online[cam_index] = False

        with frame_locks[cam_index]:
            camera_frames[cam_index] = None

        try:
            if cap is not None:
                cap.release()
        except:
            pass

        camera_online[cam_index] = False

        with frame_locks[cam_index]:
            camera_frames[cam_index] = None

        time.sleep(5)



# ==========================================
# WELLNESS CHECK
# ==========================================

last_activity_time = time.time()
last_activity_display = datetime.now().strftime("%H:%M:%S")

wellness_active = False
wellness_attempts = 0
last_prompt_time = 0

hand_raised_detected = False

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

def get_timeout():

    hour = datetime.now().hour

    if hour >= 22 or hour < 6:
        return 2 * 6

    return 1 * 6


def hand_raised(keypoints):

    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6

    LEFT_WRIST = 9
    RIGHT_WRIST = 10

    if (
        keypoints[LEFT_WRIST][2] < 0.3
        or keypoints[RIGHT_WRIST][2] < 0.3
    ):
        return False

    left_up = (
        keypoints[LEFT_WRIST][0]
        <
        keypoints[LEFT_SHOULDER][0]
    )

    right_up = (
        keypoints[RIGHT_WRIST][0]
        <
        keypoints[RIGHT_SHOULDER][0]
    )

    return left_up or right_up



def send_telegram_alert(cam_id, frame):

    try:

        message = (
            f"FALL DETECTED\n"
            f"Camera: {cam_id + 1}\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        _, buffer = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80]
        )

        image_bytes = buffer.tobytes()

        for target in TELEGRAM_TARGETS:

            try:

                files = {
                    "photo": (
                        "alert.jpg",
                        image_bytes,
                        "image/jpeg"
                    )
                }

                data = {
                    "chat_id": target["chat_id"],
                    "caption": message
                }

                url = (
                    f"https://api.telegram.org/bot"
                    f"{target['token']}/sendPhoto"
                )

                requests.post(
                    url,
                    data=data,
                    files=files,
                    timeout=10
                )

            except Exception as e:

                print(
                    f"Telegram target failed: {e}"
                )

        print("Telegram alerts sent")

    except Exception as e:

        print("Telegram error:", e)

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


def reconnect_camera_async(cam_index):

    global caps

    state = camera_states[cam_index]

    if state["reconnecting"]:
        return

    state["reconnecting"] = True

    def worker():

        try:

            print(f"[CAM {cam_index+1}] Reconnecting...")

            cap = cv2.VideoCapture(
                RTSP_URLS[cam_index],
                cv2.CAP_FFMPEG
            )

            if cap.isOpened():

                print(
                    f"[CAM {cam_index+1}] Reconnected"
                )

                caps[cam_index] = cap

            else:

                caps[cam_index] = None

        except Exception as e:

            print(
                f"[CAM {cam_index+1}] Reconnect failed: {e}"
            )

        finally:

            state["reconnecting"] = False

    threading.Thread(
        target=worker,
        daemon=True
    ).start()
    

# ==================================================
# OPEN CAMERAS
# ==================================================

for i in range(len(RTSP_URLS)):

    threading.Thread(
        target=camera_worker,
        args=(i,),
        daemon=True
    ).start()

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

        "last_seen": "Never",

        "prev_keypoints": None,

        "last_telegram_time": 0,

        "last_reconnect_attempt": 0,

        "reconnecting": False,

        "last_movement": "Never",

        "last_visible": "Never",
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


def start_wellness_check():

    global wellness_active
    global wellness_attempts
    global last_prompt_time

    wellness_active = True
    wellness_attempts = 0
    last_prompt_time = 0

    print(
        "[CHECK] Wellness check started"
    )

def process_wellness_check():

    global wellness_active
    global wellness_attempts
    global last_prompt_time

    global hand_raised_detected

    if not wellness_active:
        return

    if hand_raised_detected:

        print(
            "[CHECK] Response received"
        )

        hand_raised_detected = False

        wellness_active = False
        wellness_attempts = 0

        return

    now = time.time()

    if (
        wellness_attempts < 3
        and now - last_prompt_time > 15
    ):

    

        last_prompt_time = now

        wellness_attempts += 1

    if (
        wellness_attempts >= 3
        and now - last_prompt_time > 15
    ):

        print(
            "[CHECK] NO RESPONSE"
        )

        threading.Thread(
            target=ring_alarm,
            daemon=True
        ).start()

        send_mqtt_alert(
            -1,
            "NO_RESPONSE"
        )

        blank = np.zeros(
            (360, 640, 3),
            dtype=np.uint8
        )

        cv2.putText(
            blank,
            "NO RESPONSE",
            (120,180),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0,0,255),
            3
        )

        threading.Thread(
            target=send_telegram_alert,
            args=(-1, blank),
            daemon=True
        ).start()

        wellness_active = False

# ==================================================
# MAIN LOOP
# ==================================================

while True:

    frames = []

    current_time = time.time()

    for cam_index in range(len(RTSP_URLS)):

        state = camera_states[cam_index]


        with frame_locks[cam_index]:

            latest = camera_frames[cam_index]

        stale = (
            time.time()
            - camera_last_frame_time[cam_index]
        ) > 5

        if latest is None or stale:

            frame = np.zeros(
                (360,640,3),
                dtype=np.uint8
            )

            cv2.putText(
                frame,
                f"CAM {cam_index+1} OFFLINE",
                (120,180),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0,0,255),
                3
            )

            frames.append(frame)

            continue

        frame = latest.copy()
        
        frame = cv2.resize(frame, (640, 360))

        try:
            keypoints = detect_pose(frame)
        except Exception as e:
            print(f"Pose detection error on CAM {cam_index+1}: {e}")
            keypoints = None


        if keypoints is not None:

            avg_conf = np.mean(keypoints[:, 2])

            if avg_conf > 0.35:

                state["last_visible"] = datetime.now().strftime(
                    "%H:%M:%S"
                )

            if wellness_active:

                if hand_raised(keypoints):
                    hand_raised_detected = True

        


        # =====================================
# ACTIVITY DETECTION
# =====================================

        movement_detected = False

        if keypoints is not None:

            if state["prev_keypoints"] is not None:

                diff = np.mean(
                    np.abs(
                        keypoints[:, :2]
                        -
                        state["prev_keypoints"][:, :2]
                    )
                )

                if diff > 0.02:

                    movement_detected = True

            state["prev_keypoints"] = keypoints.copy()

        if movement_detected:

            last_activity_time = time.time()

            state["last_movement"] = datetime.now().strftime(
                "%H:%M:%S"
            )


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


                    threading.Thread(
                        target=send_telegram_alert,
                        args=(cam_index, frame.copy()),
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
            f"LAST VISIBLE: {state['last_visible']}",
            (20,310),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255,255,0),
            2
        )


        frames.append(frame)

    if (
        not wellness_active
        and
        time.time() - last_activity_time
        > get_timeout()
    ):

        start_wellness_check()

    process_wellness_check()

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

cv2.destroyAllWindows()