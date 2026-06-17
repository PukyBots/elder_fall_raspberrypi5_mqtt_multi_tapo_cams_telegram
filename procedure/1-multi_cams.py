import cv2
import numpy as np

cam1 = cv2.VideoCapture(
    "rtsp://pulkitgarg:Allenhouse@123@192.168.1.57:554/stream1"
)

cam2 = cv2.VideoCapture(
    "rtsp://pulkitgarg:Allenhouse@123@192.168.1.60:554/stream1"
)

while True:

    ret1, frame1 = cam1.read()
    ret2, frame2 = cam2.read()

    if not ret1 or not ret2:
        print("Camera frame missing")
        break

    frame1 = cv2.resize(frame1, (640, 360))
    frame2 = cv2.resize(frame2, (640, 360))

    combined = np.hstack((frame1, frame2))

    cv2.imshow("Multi Camera View", combined)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cam1.release()
cam2.release()
cv2.destroyAllWindows()