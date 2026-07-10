"""FFT spektrini tahlil qilish: chastota diapazonlari va tashxis.

Klassik vibro-diagnostika bo'yicha uch diapazon:
  0–100 Hz   — val aylanish chastotasi atrofi: balanssizlik, o'q markazsizligi
  100–300 Hz — mexanik bo'shliq, mahkamlash muammolari
  300+ Hz    — podshipnik nuqsonlari chastotalari, yeyilish

Bins formati (firmware bilan kelishilgan): i-bin chastotasi =
i * sample_rate / (2 * len(bins)); 0-bin (DC) tahlilga kirmaydi.
"""

BANDS = (
    (0.0, 100.0,
     "past chastota (0–100 Hz) ustun — balanssizlik yoki o'q markazsizligi ehtimoli"),
    (100.0, 300.0,
     "o'rta chastota (100–300 Hz) ustun — mexanik bo'shliq ehtimoli"),
    (300.0, None,
     "yuqori chastota (300+ Hz) ustun — podshipnik yeyilishi ehtimoli"),
)


# Bundan past chastotalar tahlilga kirmaydi: DC/gravitatsiya "oqishi"
# (mean-removal qilinmagan firmware'da 1-2-binlarga sizadi) tashxisni
# "balanssizlik" tomon og'dirib yubormasligi uchun. Uskuna chastotalari
# (1500+ RPM = 25+ Hz) bundan yuqorida.
LOW_CUTOFF_HZ = 10.0


def band_energies(bins, sample_rate):
    """Har bir diapazonning energiyasi (amplituda kvadratlari yig'indisi)."""
    m = len(bins)
    energies = [0.0] * len(BANDS)
    for i in range(1, m):  # DC (i=0) tashlab ketiladi
        freq = i * sample_rate / (2 * m)
        if freq < LOW_CUTOFF_HZ:
            continue
        for bi, (lo, hi, _) in enumerate(BANDS):
            if freq >= lo and (hi is None or freq < hi):
                energies[bi] += bins[i] ** 2
                break
    return energies


def diagnose(bins, sample_rate):
    """Qisqa tashxis matni (uz) yoki None (spektr bo'sh bo'lsa)."""
    if not bins or len(bins) < 2 or sample_rate <= 0:
        return None
    energies = band_energies(bins, sample_rate)
    total = sum(energies)
    if total <= 0:
        return None
    dominant = max(range(len(energies)), key=lambda i: energies[i])
    share = energies[dominant] / total * 100
    return f"{BANDS[dominant][2]} (energiya ulushi {share:.0f}%)"
