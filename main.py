"""API server — bazaga YOZADIGAN yagona joy.

Kollektor o'lchovlarni shu API ga POST qiladi; status shu yerda yagona
chegara (database.ALARM_THRESHOLD) bo'yicha aniqlanadi va anomaliyada
Telegram xabari yuboriladi (sozlamalar .env dan).

Markaziy serverda tarmoqqa ochish: uvicorn main:app --host 0.0.0.0
(oldin .env da API_KEY o'rnating — kollektor bilan bir xil qiymat).
"""
import math
import os
import time
from datetime import datetime

import requests
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel

import database

app = FastAPI()
database.init_db()

API_KEY = os.getenv("API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ALERT_COOLDOWN = 120  # soniya — BIR uskuna uchun xabarlar orasidagi minimal vaqt
_last_alert_times = {}  # bearing_name -> oxirgi xabar vaqti


def send_telegram_alert(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return  # sozlanmagan bo'lsa — jim o'tkazamiz
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.get(url, params={"chat_id": TELEGRAM_CHAT_ID, "text": message},
                     timeout=5)
    except Exception as e:
        print(f"Telegram xatolik: {e}")


class SensorInput(BaseModel):
    vibration_value: float
    bearing_name: str
    # Kollektor bufferidan kechikib kelgan o'lchovlar uchun asl vaqt
    measured_at: datetime | None = None


@app.post("/api/vibration")
def predict(data: SensorInput, background_tasks: BackgroundTasks,
            x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Noto'g'ri API kalit")
    if not math.isfinite(data.vibration_value):
        raise HTTPException(status_code=422,
                            detail="vibration_value chekli son bo'lishi kerak")

    status = "ALARM" if data.vibration_value > database.ALARM_THRESHOLD else "OK"
    database.insert_measurement(data.bearing_name, data.vibration_value, status,
                                timestamp=data.measured_at)

    if status == "ALARM":
        last = _last_alert_times.get(data.bearing_name, 0.0)
        if time.time() - last > ALERT_COOLDOWN:
            _last_alert_times[data.bearing_name] = time.time()
            # Javobni ushlab turmaslik uchun xabar fonda yuboriladi
            background_tasks.add_task(
                send_telegram_alert,
                f"⚠️ DIQQAT! {data.bearing_name}da anomaliya! "
                f"Qiymat: {data.vibration_value:.4f}")

    return {"status": status, "value": data.vibration_value}
