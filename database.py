"""Yagona ma'lumotlar bazasi qatlami.

Barcha yozish/o'qish faqat shu modul orqali. Baza manzili DATABASE_URL
muhit o'zgaruvchisidan olinadi (markaziy PostgreSQL uchun), masalan:
    DATABASE_URL=postgresql+psycopg://user:parol@host:5432/vibration
O'rnatilmagan bo'lsa — loyiha papkasidagi lokal SQLite fayl ishlatiladi
(qaysi papkadan ishga tushirilganidan qat'i nazar, yo'l absolyut).
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String,
                        Table, create_engine, func, select)

load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_SQLITE = f"sqlite:///{Path(__file__).resolve().parent / 'vibration.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE)

# Yagona ALARM chegarasi — butun loyiha shu konstantani ishlatadi
ALARM_THRESHOLD = 0.55

engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Qaysi bazaga ulanganini har doim ko'rsatamiz — DATABASE_URL unutilib
# lokal faylga yozilayotganini jimgina o'tkazib yubormaslik uchun.
if DATABASE_URL == DEFAULT_SQLITE:
    print(f"[database] DATABASE_URL o'rnatilmagan — LOKAL SQLite: {DEFAULT_SQLITE}",
          flush=True)
else:
    print(f"[database] Markaziy baza: "
          f"{engine.url.render_as_string(hide_password=True)}", flush=True)

measurements = Table(
    "measurements", metadata,
    Column("id", Integer, primary_key=True),
    Column("timestamp", DateTime),
    Column("bearing_name", String),
    Column("rms", Float),
    Column("status", String),
)


def init_db():
    """Jadval bo'lmasa yaratadi (bor bo'lsa tegmaydi)."""
    metadata.create_all(engine)


def insert_measurement(bearing_name, rms, status, timestamp=None):
    with engine.begin() as conn:
        conn.execute(measurements.insert().values(
            timestamp=timestamp or datetime.now(),
            bearing_name=bearing_name,
            rms=rms,
            status=status,
        ))


def get_latest(bearing_name):
    """Oxirgi o'lchov (rms, status, timestamp) yoki None."""
    query = (select(measurements.c.rms, measurements.c.status,
                    measurements.c.timestamp)
             .where(measurements.c.bearing_name == bearing_name)
             .order_by(measurements.c.id.desc())
             .limit(1))
    df = pd.read_sql(query, engine)
    return df.iloc[0] if not df.empty else None


def get_recent(bearing_name, limit=50):
    """Grafik uchun oxirgi N ta o'lchov (vaqt bo'yicha o'sish tartibida)."""
    query = (select(measurements.c.timestamp, measurements.c.rms)
             .where(measurements.c.bearing_name == bearing_name)
             .order_by(measurements.c.id.desc())
             .limit(limit))
    df = pd.read_sql(query, engine)
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df.sort_values('timestamp')
    return df


def get_by_date(bearing_name, day):
    """Tanlangan kundagi barcha o'lchovlar (day — datetime.date)."""
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    query = (select(measurements.c.timestamp, measurements.c.rms)
             .where(measurements.c.bearing_name == bearing_name)
             .where(measurements.c.timestamp >= start)
             .where(measurements.c.timestamp < end)
             .order_by(measurements.c.timestamp))
    return pd.read_sql(query, engine)


def get_last_date(bearing_name):
    """Oxirgi yozuv sanasi (hisobot uchun default). Bo'lmasa — bugun."""
    with engine.connect() as conn:
        last = conn.execute(
            select(func.max(measurements.c.timestamp))
            .where(measurements.c.bearing_name == bearing_name)
        ).scalar()
    if last is None:
        return datetime.now().date()
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    return last.date()


if __name__ == "__main__":
    init_db()
    print(f"✅ Baza tayyor: {engine.url}")
