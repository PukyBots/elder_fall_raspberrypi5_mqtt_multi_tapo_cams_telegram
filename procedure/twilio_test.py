import cloudinary
import cloudinary.uploader
from twilio.rest import Client

# Cloudinary
cloudinary.config(
    cloud_name="dl2fhwcl5",
    api_key="971978761231223",
    api_secret="G71zlwDG-zH65inED7kJn55px1M"
)

# Twilio
ACCOUNT_SID = "AC77887f9c53cbc897caaa895720a3d88e"
AUTH_TOKEN = "5cdf7097f3879db06e14bf06441b3a1d"

client = Client(ACCOUNT_SID, AUTH_TOKEN)

TWILIO_WHATSAPP = "whatsapp:+14155238886"  # Sandbox
TO_WHATSAPP = "whatsapp:+918953193403"

IMAGE_PATH = "/home/tce/real_box.jpg"

try:
    # Upload image
    result = cloudinary.uploader.upload(IMAGE_PATH)
    image_url = result["secure_url"]

    print("Uploaded to Cloudinary:")
    print(image_url)

    # Send WhatsApp
    message = client.messages.create(
        from_=TWILIO_WHATSAPP,
        to=TO_WHATSAPP,
        body="Test image from Python",
        media_url=[image_url]
    )

    print("WhatsApp sent successfully")
    print("SID:", message.sid)

except Exception as e:
    print("Error:", e)
