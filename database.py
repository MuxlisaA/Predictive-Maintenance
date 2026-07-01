import sqlite3
from datetime import datetime

DB_NAME = "vibration.db"

def init_db():
    """Baza jadvalini noldan yaratish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Eslatma: jadval nomi 'measurements' deb belgilandi
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

def insert_vibration(bearing_name, rms, status):
    """Ma'lumotlarni bazaga yozish"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO measurements (timestamp, bearing_name, rms, status)
        VALUES (?, ?, ?, ?)
    """, (timestamp, bearing_name, rms, status))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("✅ Baza va 'measurements' jadvali tayyor.")