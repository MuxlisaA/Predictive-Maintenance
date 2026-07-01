import serial
import requests
import time
import sqlite3


last_alert_time = 0 
# --- Telegram orqali xabar yuborish ---
def send_telegram_alert(message):
    token = "8764994809:AAG4Htoj8JqEImzjwoVJxdXPVJr2Y-W_fhQ"
    chat_id = "6631268838"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={message}"
    try:
        requests.get(url, timeout=5)
    except Exception as e:
        print(f"Telegram xatolik: {e}")

# --- Bazaga saqlash ---
# def save_to_db(bearing_name, rms):
#     conn = sqlite3.connect('vibration.db')
#     cursor = conn.cursor()
#     status = "OK" if rms < 0.55 else "ALARM"
#     cursor.execute("INSERT INTO measurements (bearing_name, rms, status, timestamp) VALUES (?, ?, ?, ?)",
#                    (bearing_name, rms, status, time.strftime('%Y-%m-%d %H:%M:%S')))
#     conn.commit()
#     conn.close()
    
#     # Agar anomaliya bo'lsa, xabar yuborish
#     if rms > 0.55:
#         send_telegram_alert(f"⚠️ DIQQA! {bearing_name}da anomaliya! Qiymat: {rms:.4f}")
# Faylning eng yuqori qismiga bitta o'zgaruvchi qo'shing


def save_to_db(bearing_name, rms):
    global last_alert_time  # Global o'zgaruvchini ishlatamiz
    
    conn = sqlite3.connect('vibration.db')
    cursor = conn.cursor()
    status = "OK" if rms < 0.55 else "ALARM"
    cursor.execute("INSERT INTO measurements (bearing_name, rms, status, timestamp) VALUES (?, ?, ?, ?)",
                   (bearing_name, rms, status, time.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    
    # Anomaliya vaqtini tekshirish (faqat ALARM holatida)
    if rms > 0.55:
        # Agar oxirgi xabardan 120 soniya (2 daqiqa) o'tgan bo'lsa
        if time.time() - last_alert_time > 120:
            send_telegram_alert(f"⚠️ DIQQA! {bearing_name}da anomaliya! Qiymat: {rms:.4f}")
            last_alert_time = time.time() # Vaqtni yangilaymiz
# --- Asosiy qism ---
ser = serial.Serial('COM3', 115200, timeout=2) 
API_URL = "http://127.0.0.1:8000/api/vibration"

print("🚀 Ma'lumotlarni yig'ish boshlandi...")

while True:
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if line.startswith("DATA:"):
                raw_data = line.replace("DATA:", "").split(",")
                val = sum([abs(float(x)) for x in raw_data]) / 3
                
                # 1. Bazaga yozish va botni tekshirish
                save_to_db("Bearing 4 (Motor)", val)
                
                # 2. Serverga yuborish
                payload = {"vibration_value": val, "bearing_name": "Bearing 4 (Motor)"}
                response = requests.post(API_URL, json=payload, timeout=2) 
                
                print(f"Yuborildi: {val:.4f} | Status: {response.status_code}")
                
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
        time.sleep(1)