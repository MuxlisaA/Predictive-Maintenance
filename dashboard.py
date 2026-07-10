from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from analysis import diagnose
from database import (ALARM_THRESHOLD, get_by_date, get_last_date,
                      get_latest, get_latest_spectrum, get_recent, init_db)

init_db()

SPECTRUM_MAX_AGE = 600  # soniya — bundan eski spektr bo'yicha tashxis berilmaydi


@st.fragment(run_every="1s")
def render_realtime(bearing_name):
    """Real-vaqt panel. st.fragment tufayli FAQAT shu blok har soniyada
    yangilanadi — butun sahifa (va tab2 hisobotlari) qayta yuklanmaydi."""
    latest = get_latest(bearing_name)
    if latest is not None:
        col1, col2, col3 = st.columns(3)
        col1.metric("USKUNA HOLATI",
                    "🚨 ALARM" if latest['rms'] > ALARM_THRESHOLD else "✅ OK")
        col2.metric("TEBRANISH (RMS)", f"{latest['rms']:.4f} g")
        col3.metric("OXIRGI YANGILANISH",
                    pd.to_datetime(latest['timestamp']).strftime('%H:%M:%S'))

        chart_data = get_recent(bearing_name)
        if not chart_data.empty:
            chart = alt.Chart(chart_data).mark_line(point=True).encode(
                x=alt.X('timestamp:T', axis=alt.Axis(format='%H:%M:%S', title='Vaqt')),
                y=alt.Y('rms:Q', title='Tebranish (g)'),
                tooltip=['timestamp', 'rms']
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)

        # FFT spektri (firmware yuborsa) + tashxis
        spec = get_latest_spectrum(bearing_name)
        if spec:
            m = len(spec['bins'])
            freqs = [i * spec['sample_rate'] / (2 * m) for i in range(m)]
            sdf = pd.DataFrame({"chastota": freqs, "amplituda": spec['bins']})
            st.markdown("#### 🎛 Chastota spektri (FFT)")
            spec_chart = alt.Chart(sdf).mark_bar().encode(
                x=alt.X('chastota:Q', title='Chastota (Hz)'),
                y=alt.Y('amplituda:Q', title='Amplituda'),
                tooltip=[alt.Tooltip('chastota:Q', title='Hz', format='.0f'),
                         alt.Tooltip('amplituda:Q', title='Amplituda', format='.4f')]
            ).properties(height=250)
            st.altair_chart(spec_chart, use_container_width=True)
            age = (datetime.now() - spec['received_at']).total_seconds()
            if age < SPECTRUM_MAX_AGE:
                diag = diagnose(spec['bins'], spec['sample_rate'])
                if diag:
                    st.info(f"🩺 Tashxis: {diag}")
                st.caption(f"Spektr vaqti: {spec['timestamp'].strftime('%H:%M:%S')}")
            else:
                # Eski spektr bo'yicha tashxis chalg'itadi — faqat ogohlantirish
                st.caption("⚠️ Spektr eski (oxirgisi: "
                           f"{spec['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}) — "
                           "tashxis ko'rsatilmaydi")
    else:
        st.warning("Ma'lumot topilmadi.")


# --- Dashboard Dizayni ---
st.set_page_config(page_title="Predictive Maintenance", layout="wide")

st.sidebar.markdown("## ⚙️ Boshqaruv Paneli")
selected_bearing = st.sidebar.radio("Qurilmani tanlang:",
    ["Bearing 1 (Main Drive)", "Bearing 2 (Fan)", "Bearing 3 (Pump)", "Bearing 4 (Motor)"], index=3)

st.markdown(f"# 📊 {selected_bearing} Monitoringi")
tab1, tab2 = st.tabs(["📊 Real-vaqt Monitoring", "📋 Tahliliy Hisobotlar"])

# --- AVTOMATIK YANGILANISH MANTIG'I ---
with tab1:
    # Real-vaqt panel st.fragment ichida: tab2 ga tegmasdan har soniyada
    # o'zini-o'zi yangilaydi (avvalgi time.sleep+st.rerun butun skriptni
    # to'xtatib, tab2 hech qachon render bo'lmasligiga sabab bo'lardi).
    render_realtime(selected_bearing)
# --- Tab2 (Tahliliy Hisobotlar) ---


with tab2:
    st.markdown("### 🔍 Tarixiy va Davriy Tahlil")

    col_s1, col_s2, col_s3 = st.columns(3)
    period = col_s1.selectbox("Davriylik:", ["Kunlik", "Haftalik", "Oylik", "Yillik"], key="period_key")
    search_date = col_s2.date_input("Sanani tanlang:", value=get_last_date(selected_bearing), key="date_key")

    if col_s3.button("Hisobotni ko'rsatish"):
        df = get_by_date(selected_bearing, search_date)

        # Agar df bo'sh bo'lsa, bazada aynan shu sana va nomda yozuv yo'q
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Grafik
            if period == "Kunlik":
                # Kunni 24 ta soatga bo'lamiz: har bir soat uchun o'rtacha RMS.
                # Butun kun ko'rinishi uchun 24 ta soat (00:00–23:00) o'qda
                # qoladi, ma'lumot bo'lmagan soatlar bo'sh slot bo'lib turadi.
                # Ikki bosqichli o'rtacha (daqiqa -> soat): normal rejimda
                # daqiqasiga 1 agregat, ALARM'da sekundiga ~8 xom qator
                # keladi — to'g'ridan-to'g'ri soatlik mean ALARM qatorlarini
                # og'irroq tortib yuborardi.
                hourly = (df.set_index('timestamp')[['rms']]
                            .resample('min').mean()
                            .resample('h').mean().dropna().reset_index())
                hourly['soat'] = hourly['timestamp'].dt.strftime('%H:00')
                all_hours = [f"{h:02d}:00" for h in range(24)]
                chart = alt.Chart(hourly).mark_bar().encode(
                    x=alt.X('soat:O', title="Soat", sort=all_hours,
                            scale=alt.Scale(domain=all_hours)),
                    y=alt.Y('rms:Q', title="O'rtacha tebranish (g)"),
                    tooltip=[alt.Tooltip('soat:O', title='Soat'),
                             alt.Tooltip('rms:Q', title='RMS', format='.4f')]
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)
            else:
                # Uzoq davrlar uchun o'rtacha bilan guruhlash
                freq_map = {"Haftalik": "D", "Oylik": "W", "Yillik": "ME"}
                chart_df = df.set_index('timestamp')[['rms']].resample(freq_map[period]).mean()
                st.line_chart(chart_df)
            st.dataframe(df)
        else:
            # Xatolikni aniqroq ko'rish uchun
            st.error(f"Ma'lumot topilmadi: {selected_bearing} | {search_date}")
