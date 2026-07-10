"""Eski lokal vibration.db (SQLite) dagi o'lchovlarni markaziy bazaga
(DATABASE_URL) ko'chirish.

- Eski arxitekturaning ikki marta yozilgan nusxalari (kollektor + API
  bir xil o'lchovni ikki qator qilib yozardi) bitta qatorga yig'iladi.
- Maqsad bazada allaqachon bor qatorlar tashlab ketiladi — skriptni
  xohlagancha qayta ishga tushirish xavfsiz (yangi hech narsa buzilmaydi).
- Status yagona chegara (ALARM_THRESHOLD) bo'yicha qayta hisoblanadi.

Ishga tushirish:
    DATABASE_URL=postgresql+psycopg://... python migrate_db.py [eski_db_yoli]
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

import database


def migrate(old_db_path):
    old_db_path = Path(old_db_path).resolve()
    if not old_db_path.exists():
        sys.exit(f"Manba topilmadi: {old_db_path}\n"
                 "Eski vibration.db qaysi mashinada bo'lsa, skriptni o'sha "
                 "yerda ishga tushiring yoki yo'lni argument qilib bering.")

    # O'zini-o'ziga ko'chirishdan himoya (DATABASE_URL o'rnatilmagan holat)
    url = database.engine.url
    if url.get_backend_name() == "sqlite" and url.database:
        if Path(url.database).resolve() == old_db_path:
            sys.exit("Manba va maqsad bir xil fayl. Markaziy baza uchun "
                     "DATABASE_URL muhit o'zgaruvchisini o'rnating.")

    src = sqlite3.connect(old_db_path)
    rows = src.execute(
        "SELECT timestamp, bearing_name, rms FROM measurements ORDER BY id"
    ).fetchall()
    src.close()
    if not rows:
        sys.exit("Manba bazada yozuv yo'q — ko'chirishga hojat yo'q.")

    # 1) Manba ichidagi aynan bir xil (vaqt, uskuna, rms) nusxalarni yig'ish
    seen, unique = set(), []
    for ts, name, rms in rows:
        key = (datetime.fromisoformat(ts), name, rms)
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    dups_in_source = len(rows) - len(unique)

    # 2) Maqsad bazada allaqachon borlarini tashlab ketish (idempotentlik)
    database.init_db()
    m = database.measurements
    with database.engine.connect() as conn:
        existing = {
            (ts, name, rms) for ts, name, rms in
            conn.execute(select(m.c.timestamp, m.c.bearing_name, m.c.rms))
        }
    to_insert = [k for k in unique if k not in existing]

    if not to_insert:
        print(f"Yangi yozuv yo'q: manbadagi {len(unique)} ta noyob o'lchov "
              "maqsad bazada allaqachon bor.")
        return

    records = [{
        "timestamp": ts,
        "bearing_name": name,
        "rms": rms,
        "status": "ALARM" if rms > database.ALARM_THRESHOLD else "OK",
    } for ts, name, rms in to_insert]

    with database.engine.begin() as conn:
        conn.execute(m.insert(), records)

    print(f"✅ {len(records)} ta yozuv ko'chirildi: {old_db_path} -> {url}\n"
          f"   (manbada {len(rows)} qator, {dups_in_source} ta ikki nusxa "
          f"yig'ildi, {len(unique) - len(records)} tasi allaqachon bor edi)")


if __name__ == "__main__":
    default_src = Path(__file__).resolve().parent / "vibration.db"
    migrate(sys.argv[1] if len(sys.argv) > 1 else default_src)
