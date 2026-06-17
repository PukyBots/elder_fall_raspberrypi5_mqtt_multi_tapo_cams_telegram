import cv2

rtsp_url = "rtsp://pulkitgarg:Allenhouse@123@192.168.1.57:554/stream1"

cap = cv2.VideoCapture(rtsp_url)

while True:
    ret, frame = cap.read()

    if not ret:
        print("Frame not received")
        break

    cv2.imshow("Tapo Stream", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()