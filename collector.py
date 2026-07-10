"""Datchik mashinasida ishlaydi: serial portdan o'qiydi va API ga yuboradi.

Bazaga yozish va Telegram xabarlari — server tomonda (main.py).
Sozlamalar .env orqali: SERIAL_PORT, API_URL, BEARING_NAME, API_KEY.

API vaqtincha ishlamay qolsa, o'lchovlar xotiradagi buferda saqlanadi
(oxirgi ~2 soat) va aloqa tiklangach asl vaqti bilan yuboriladi.
"""
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import requests
import serial
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
BAUD_RATE = 115200
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/vibration")
BEARING_NAME = os.getenv("BEARING_NAME", "Bearing 4 (Motor)")
API_KEY = os.getenv("API_KEY", "")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}

# ~2 soat (sekundiga 1 o'lchovda); to'lsa eng eskisi tushib qoladi
buffer = deque(maxlen=7200)


def open_serial():
    """Portni ochadi; ochilmasa qayta urinadi (kabel sug'urilgan va h.k.)."""
    while True:
        try:
            s = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            print(f"🔌 Port ochildi: {SERIAL_PORT}")
            return s
        except serial.SerialException as e:
            print(f"Port ochilmadi ({e}) — 5 soniyadan keyin qayta urinamiz...")
            time.sleep(5)


def flush_buffer():
    """Bufferdagi o'lchovlarni navbat bilan yuboradi; xato bo'lsa to'xtaydi
    (qolganlari keyingi urinishda ketadi)."""
    while buffer:
        payload = buffer[0]
        response = requests.post(API_URL, json=payload, headers=HEADERS, timeout=5)
        response.raise_for_status()
        buffer.popleft()
        print(f"Yuborildi: {payload['vibration_value']:.4f} "
              f"| Status: {response.status_code} | Buferda: {len(buffer)}")


ser = open_serial()
print("🚀 Ma'lumotlarni yig'ish boshlandi...")

while True:
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()

            if line.startswith("DATA:"):
                raw_data = line.replace("DATA:", "").split(",")
                val = sum([abs(float(x)) for x in raw_data]) / 3

                buffer.append({
                    "vibration_value": val,
                    "bearing_name": BEARING_NAME,
                    "measured_at": datetime.now().isoformat(),
                })
                flush_buffer()
        else:
            time.sleep(0.05)  # bo'sh aylanishda protsessorni band qilmaslik

    except serial.SerialException as e:
        print(f"Serial xatolik: {e} — portni qayta ochamiz")
        try:
            ser.close()
        except Exception:
            pass
        ser = open_serial()
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
        time.sleep(1)
