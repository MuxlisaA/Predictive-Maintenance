"""API server — bazaga YOZADIGAN yagona joy.

Kollektor o'lchov va spektrlarni shu API ga POST qiladi; status shu yerda
yagona chegara (database.ALARM_THRESHOLD) bo'yicha aniqlanadi va anomaliyada
Telegram xabari yuboriladi (tashxis + dashboard havolasi bilan).

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

import analysis
import database

app = FastAPI()
database.init_db()

API_KEY = os.getenv("API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
ALERT_COOLDOWN = 120  # soniya — BIR uskuna uchun xabarlar orasidagi minimal vaqt
SPECTRUM_MAX_AGE = 600  # soniya — bundan eski spektr tashxisga ishlatilmaydi
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


def build_alert_text(bearing_name, value):
    """Xabar: qiymat + chegaradan oshish + (yangi spektr bo'lsa) tashxis
    + dashboard havolasi."""
    over = (value / database.ALARM_THRESHOLD - 1) * 100
    lines = [f"⚠️ DIQQAT! {bearing_name}da anomaliya!",
             f"Qiymat: {value:.4f} g (chegaradan {over:.0f}% yuqori)"]
    spec = database.get_latest_spectrum(bearing_name)
    # Yangilik server soati bo'yicha (received_at) — kollektor mashinasining
    # soati serverdan farq qilsa ham tekshiruv buzilmaydi
    if spec and (datetime.now() - spec["received_at"]).total_seconds() < SPECTRUM_MAX_AGE:
        diag = analysis.diagnose(spec["bins"], spec["sample_rate"])
        if diag:
            lines.append(f"Tashxis: {diag}")
    if DASHBOARD_URL:
        lines.append(f"📊 Dashboard: {DASHBOARD_URL}")
    return "\n".join(lines)


def check_api_key(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Noto'g'ri API kalit")


class SensorInput(BaseModel):
    vibration_value: float
    bearing_name: str
    # Kollektor bufferidan kechikib kelgan o'lchovlar uchun asl vaqt
    measured_at: datetime | None = None


class SpectrumInput(BaseModel):
    bearing_name: str
    sample_rate: float
    bins: list[float]
    measured_at: datetime | None = None


@app.get("/api/config")
def config():
    """Kollektor uchun umumiy sozlamalar (chegara — yagona manbadan)."""
    return {"alarm_threshold": database.ALARM_THRESHOLD}


@app.post("/api/vibration")
def predict(data: SensorInput, background_tasks: BackgroundTasks,
            x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
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
                build_alert_text(data.bearing_name, data.vibration_value))

    return {"status": status, "value": data.vibration_value}


@app.post("/api/spectrum")
def spectrum(data: SpectrumInput, x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    if not math.isfinite(data.sample_rate) or data.sample_rate <= 0:
        raise HTTPException(status_code=422,
                            detail="sample_rate musbat son bo'lishi kerak")
    if not 2 <= len(data.bins) <= 4096 or not all(map(math.isfinite, data.bins)):
        raise HTTPException(status_code=422,
                            detail="bins — 2..4096 ta chekli son bo'lishi kerak")

    database.insert_spectrum(data.bearing_name, data.sample_rate, data.bins,
                             timestamp=data.measured_at)
    return {"ok": True, "bins": len(data.bins)}
