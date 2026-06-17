import cv2
import numpy as np
import tensorflow as tf
import math

# ==========================
# CONFIG
# ==========================

# RTSP_URL = "rtsp://pulkitgarg:pulkitgarg@192.168.247.32:554/stream1"
RTSP_URL  = "rtsp://pulkitgarg:Allenhouse@123@192.168.1.57:554/stream1"
MODEL_PATH = "movenet_singlepose_thunder.tflite"

# ==========================
# LOAD MODEL
# ==========================

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

def classify_posture(keypoints, threshold=0.1):

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

    elif hip_to_knee < 0.20:
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

# ==========================
# VIDEO
# ==========================

cap = cv2.VideoCapture(RTSP_URL)

if not cap.isOpened():
    print("Cannot open RTSP stream")
    exit()

while True:

    ret, frame = cap.read()

    if not ret:
        print("Frame not received")
        break

    frame = cv2.resize(frame, (960, 540))

    keypoints = detect_pose(frame)

    draw_pose(frame, keypoints)

    posture = classify_posture(keypoints)

    cv2.putText(
        frame,
        f"POSTURE: {posture}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 255),
        2
    )

    cv2.imshow(
        "MoveNet - Tapo Camera",
        frame
    )

    key = cv2.waitKey(1)

    if key == 27:
        break

cap.release()
cv2.destroyAllWindows()