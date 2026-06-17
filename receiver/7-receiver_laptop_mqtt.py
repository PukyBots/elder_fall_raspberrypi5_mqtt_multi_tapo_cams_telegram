#python -m venv mp_env
#./mp_env/Scripts/activate
#pip install paho-mqtt
#pip install opencv-python

import paho.mqtt.client as mqtt
import json

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())

    print("\nALERT RECEIVED")
    print("Camera:", data["camera"])
    print("Event :", data["event"])
    print("Time  :", data["time"])

client = mqtt.Client()
client.on_message = on_message

client.connect("broker.hivemq.com", 1883, 60)

client.subscribe("eldercare/alert")

print("Waiting for alerts...")
client.loop_forever()