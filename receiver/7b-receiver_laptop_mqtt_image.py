#python -m venv mp_env
#./mp_env/Scripts/activate
#pip install paho-mqtt
#pip install opencv-python

import paho.mqtt.client as mqtt
import json
import base64
import cv2
import numpy as np
import os
from datetime import datetime

SAVE_FOLDER = "dashboard/alerts"

os.makedirs(
    SAVE_FOLDER,
    exist_ok=True
)

def on_message(client, userdata, msg):

    data = json.loads(
        msg.payload.decode()
    )

    print("\n========== ALERT ==========")
    print("Camera :", data["camera"])
    print("Event  :", data["event"])
    print("Time   :", data["time"])

    if "image" in data:

        image_bytes = base64.b64decode(
            data["image"]
        )

        np_arr = np.frombuffer(
            image_bytes,
            np.uint8
        )

        image = cv2.imdecode(
            np_arr,
            cv2.IMREAD_COLOR
        )

        filename = (
            f"cam{data['camera']}_"
            f"{data['event']}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        )

        filepath = os.path.join(
            SAVE_FOLDER,
            filename
        )

        cv2.imwrite(
            filepath,
            image
        )

        print(
            "Snapshot saved:",
            filepath
        )

        cv2.imshow(
            f"Alert Cam {data['camera']}",
            image
        )

        cv2.waitKey(1)

client = mqtt.Client()

client.on_message = on_message

client.connect(
    "broker.hivemq.com",
    1883,
    60
)

client.subscribe(
    "eldercare/alert"
)

print("Waiting for alerts...")

client.loop_forever()