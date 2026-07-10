"""Datchik mashinasida ishlaydi (gateway / edge): serial portdan o'qiydi,
filtrlaydi va API ga yuboradi.

Edge-mantiq (trafik tejash):
- NORMAL holatda o'lchovlar AGGREGATE_SECONDS oynasida yig'ilib, oynaning
  O'RTACHASI bitta qator bo'lib yuboriladi (default: 1 daqiqa).
- Chegaradan (serverdagi /api/config dan olinadi) OSHGAN o'lchov darhol,
  xom holida yuboriladi.
- Spektrlar (SPEC: qatorlar) normalda SPECTRUM_INTERVAL da bittadan,
  anomaliyada darhol yuboriladi.

Serial protokol (firmware bilan kelishuv):
  DATA:x,y,z            — bitta o'lchov (3 o'q)
  SPEC:<fs>:<a0,a1,...> — on-device FFT spektri; i-bin chastotasi =
                          i * fs / (2 * bins_soni)

API vaqtincha ishlamasa, yuborilmagan narsalar xotira buferida turadi
(oxirgi ~2 soat) va aloqa tiklangach asl vaqti bilan ketadi.
"""
import math
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
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/vibration")
API_BASE = API_URL.rsplit("/", 1)[0]  # .../api
BEARING_NAME = os.getenv("BEARING_NAME", "Bearing 4 (Motor)")
API_KEY = os.getenv("API_KEY", "")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
AGGREGATE_SECONDS = float(os.getenv("AGGREGATE_SECONDS", "60"))  # 0 = hammasi
SPECTRUM_INTERVAL = float(os.getenv("SPECTRUM_INTERVAL", "60"))
SPEC_BINS = int(os.getenv("SPEC_BINS", "128"))  # firmware SAMPLES/2 bilan mos
DEFAULT_THRESHOLD = 0.55

# ~2 soat (sekundiga 1 yozuvda); to'lsa eng eskisi tushib qoladi
buffer = deque(maxlen=7200)


def fetch_threshold():
    """ALARM chegarasi — yagona manba serverda (/api/config)."""
    try:
        r = requests.get(f"{API_BASE}/config", headers=HEADERS, timeout=5)
        value = float(r.json()["alarm_threshold"])
        print(f"⚙️ Chegara serverdan olindi: {value}")
        return value
    except Exception as e:
        print(f"⚙️ /api/config o'qilmadi ({e}) — default {DEFAULT_THRESHOLD}")
        return DEFAULT_THRESHOLD


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


_last_net_err_print = 0.0


def flush_buffer():
    """Bufferdagilarni navbat bilan yuboradi.
    - Tarmoq xatosi / 5xx: to'xtaydi, keyingi urinishda davom etadi.
    - 4xx: server bu yozuvni HECH QACHON qabul qilmaydi — tashlab yuboriladi,
      aks holda bitta buzuq yozuv navbat boshini abadiy band qilib, ortidagi
      ALARM'larni ham to'sib qo'yadi."""
    global _last_net_err_print
    while buffer:
        url, payload = buffer[0]
        try:
            response = requests.post(url, json=payload, headers=HEADERS, timeout=5)
        except requests.RequestException as e:
            if time.monotonic() - _last_net_err_print > 10:
                _last_net_err_print = time.monotonic()
                print(f"API bilan aloqa yo'q ({type(e).__name__}) — "
                      f"buferda {len(buffer)} ta yozuv kutmoqda")
            return
        if 400 <= response.status_code < 500:
            buffer.popleft()
            print(f"⚠️ Server rad etdi ({response.status_code}): "
                  f"{response.text[:120]} — yozuv tashlab yuborildi")
            continue
        if response.status_code >= 500:
            print(f"Server xatosi {response.status_code} — keyinroq qayta uriniladi")
            return
        buffer.popleft()
        print(f"Yuborildi -> {url.rsplit('/', 1)[1]} "
              f"| Status: {response.status_code} | Buferda: {len(buffer)}")


def queue_measurement(value):
    buffer.append((API_URL, {
        "vibration_value": value,
        "bearing_name": BEARING_NAME,
        "measured_at": datetime.now().isoformat(),
    }))


alarm_threshold = fetch_threshold()
window = []            # normal o'lchovlar yig'iladigan oyna
window_started = time.monotonic()
last_spectrum_sent = 0.0
last_value = 0.0

ser = open_serial()
print("🚀 Ma'lumotlarni yig'ish boshlandi...")

while True:
    try:
        # Oyna muddati tugagan bo'lsa — o'rtachani yuborish (sensor jim
        # bo'lsa ham ishlashi uchun har aylanishda tekshiriladi)
        if window and AGGREGATE_SECONDS > 0 and \
                time.monotonic() - window_started >= AGGREGATE_SECONDS:
            queue_measurement(sum(window) / len(window))
            window.clear()
            window_started = time.monotonic()
            flush_buffer()

        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()

            if line.startswith("DATA:"):
                try:
                    raw_data = line.replace("DATA:", "").split(",")
                    if len(raw_data) != 3:
                        continue  # chala qator (3 o'q emas) — qiymat noto'g'ri chiqadi
                    val = sum([abs(float(x)) for x in raw_data]) / 3
                except ValueError:
                    continue  # chala/buzuq qator — tashlab ketamiz
                if not math.isfinite(val):
                    continue  # 'nan'/'inf' oyna o'rtachasini zaharlamasin
                last_value = val

                if val > alarm_threshold or AGGREGATE_SECONDS <= 0:
                    # Anomaliya — darhol, xom holida
                    queue_measurement(val)
                    flush_buffer()
                else:
                    window.append(val)

            elif line.startswith("SPEC:"):
                try:
                    _, fs_str, bins_str = line.split(":", 2)
                    fs = float(fs_str)
                    bins = [float(x) for x in bins_str.split(",")]
                except ValueError:
                    continue
                # Chala kelgan SPEC noto'g'ri chastota o'qi bilan saqlanmasin:
                # bins soni firmware'dagi SAMPLES/2 (SPEC_BINS) ga teng bo'lishi shart
                if len(bins) != SPEC_BINS or not math.isfinite(fs) or fs <= 0 \
                        or not all(map(math.isfinite, bins)):
                    print(f"⚠️ SPEC tashlab yuborildi: bins={len(bins)} "
                          f"(kutilgan {SPEC_BINS}), fs={fs_str}")
                    continue
                now = time.monotonic()
                # Normalda kamdan-kam, anomaliyada darhol
                if last_value > alarm_threshold or \
                        now - last_spectrum_sent >= SPECTRUM_INTERVAL:
                    last_spectrum_sent = now
                    buffer.append((f"{API_BASE}/spectrum", {
                        "bearing_name": BEARING_NAME,
                        "sample_rate": fs,
                        "bins": bins,
                        "measured_at": datetime.now().isoformat(),
                    }))
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
