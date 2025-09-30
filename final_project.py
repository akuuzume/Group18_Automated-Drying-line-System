import adafruit_dht
import RPi.GPIO as GPIO
import board
import pyrebase
import time
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

# --- Firestore Setup ---
cred = credentials.Certificate("/home/pi/Desktop/tst/serviceAccountKey.json")
firebase_admin.initialize_app(cred)
fs_db = firestore.client()

# --- Realtime Database Setup ---
firebase_config = {
    "apiKey": "AIzaSyBrClIl4zLg-Kc91wDf5l_Whdbv5XEUmNs",
    "authDomain": "clotheslinemobile.firebaseapp.com",
    "databaseURL": "https://clotheslinemobile-default-rtdb.firebaseio.com/",
    "storageBucket": "clotheslinemobile.appspot.com"
}

firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()

# GPIO setup
GPIO.setmode(GPIO.BCM)

# Updated pins
LDR_PIN = 16       # LDR
DHT_PIN = 23       # DHT22
IN1 = 22           # Motor pin 1
IN2 = 27           # Motor pin 2

GPIO.setup(LDR_PIN, GPIO.IN)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)

# Initialize DHT22 sensor
dht_device = adafruit_dht.DHT22(DHT_PIN)

# Track last action
last_action = None

def extend_cover():
    global last_action
    if last_action != "extend":
        GPIO.output(IN1, GPIO.LOW)     # anticlockwise
        GPIO.output(IN2, GPIO.HIGH)
        last_action = "extend"
        print("Cover extending (anticlockwise)")
    else:
        stop_motor()
        print("Cover already extended, no action taken")

def retract_cover():
    global last_action
    if last_action != "retract":
        GPIO.output(IN1, GPIO.HIGH)    # clockwise
        GPIO.output(IN2, GPIO.LOW)
        last_action = "retract"
        print("Cover retracting (clockwise)")
    else:
        stop_motor()
        print("Cover already retracted, no action taken")

def stop_motor():
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)

try:
    while True:
        try:
            doc = fs_db.collection("coverSystem").document("status").get()
            manual_override = False
            status = ""
            temperature = None
            humidity = None
            ldr_value = None

            if doc.exists:
                data = doc.to_dict()
                is_extended = data.get("isExtended", None)
                updated_at = data.get("updatedAt", None)

                if is_extended is not None and updated_at is not None:
                    now = datetime.now(timezone.utc)
                    time_difference = now - updated_at

                    if time_difference.total_seconds() <= 10800:  # 3 hours
                        manual_override = True
                        if is_extended:
                            extend_cover()
                            status = "Manual override: extend cover (within last 3 hrs)"
                        else:
                            retract_cover()
                            status = "Manual override: retract cover (within last 3 hrs)"
                        print(status)

            if not manual_override:
                temperature = dht_device.temperature
                humidity = dht_device.humidity
                ldr_value = GPIO.input(LDR_PIN)

                if humidity is not None and temperature is not None:
                    print(f"Temperature: {temperature:.1f} C, Humidity: {humidity:.1f}%")
                else:
                    print("Failed to read from DHT22 sensor")
                    humidity = 0
                    temperature = 0

                print(f"LDR Value: {ldr_value} (1 = Bright, 0 = Dark)")

                if humidity > 80:
                    extend_cover()
                    status = "High humidity (>80%) detected, extending cover to protect from rain"
                elif ldr_value == 1:
                    retract_cover()
                    status = "Extreme sunlight detected, retracting cover for drying"
                else:
                    stop_motor()
                    status = "No rain or extreme sunlight, cover stopped"
                print(status)

                # Upload sensor data
                data = {
                    "temperature": temperature,
                    "humidity": humidity,
                    "ldr": ldr_value,
                    "cover_status": status,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                db.child("sensorData").push(data)
                print("Data uploaded to Firebase.")

            time.sleep(5)

        except RuntimeError as error:
            print(f"DHT reading error: {error}")
            time.sleep(2)
            continue
