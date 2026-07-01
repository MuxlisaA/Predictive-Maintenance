from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import sqlite3
import datetime

app = FastAPI()
DB_NAME = 'vibration.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            bearing_name TEXT,
            rms REAL,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

class SensorInput(BaseModel):
    vibration_value: float
    bearing_name: str 

@app.post("/api/vibration")
def predict(data: SensorInput):
    # status ni avtomatik aniqlash
    status = "ALARM" if data.vibration_value > 0.35 else "OK"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO measurements (timestamp, bearing_name, rms, status) 
        VALUES (?, ?, ?, ?)
    """, (now, data.bearing_name, data.vibration_value, status))
    conn.commit()
    conn.close()
    
    return {"status": status, "value": data.vibration_value}
