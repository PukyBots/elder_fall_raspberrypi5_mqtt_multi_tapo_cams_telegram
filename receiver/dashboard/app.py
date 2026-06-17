from flask import Flask, render_template
import paho.mqtt.client as mqtt
import json
import base64
import cv2
import numpy as np
import os
from datetime import datetime
import threading
from flask import send_from_directory

app = Flask(__name__)

SAVE_FOLDER = "alerts"
os.makedirs(SAVE_FOLDER, exist_ok=True)

events = []

# ==========================================
# MQTT CALLBACK
# ==========================================

def on_message(client, userdata, msg):

    global events

    data = json.loads(msg.payload.decode())

    filename = None

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

        cv2.imwrite(
            os.path.join(
                SAVE_FOLDER,
                filename
            ),
            image
        )

    event = {
        "camera": data["camera"],
        "event": data["event"],
        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "image": filename
    }

    events.insert(0, event)

    events = events[:100]

    print("EVENT:", event)

# ==========================================
# MQTT THREAD
# ==========================================

def mqtt_thread():

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

    client.loop_forever()

threading.Thread(
    target=mqtt_thread,
    daemon=True
).start()

# ==========================================
# WEB ROUTES
# ==========================================

@app.route("/")
def index():

    latest = events[0] if events else None

    return render_template(
        "index.html",
        latest=latest,
        events=events
    )

@app.route("/static_alert/<filename>")
def static_alert(filename):

    return send_from_directory(
        SAVE_FOLDER,
        filename
    )

# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )