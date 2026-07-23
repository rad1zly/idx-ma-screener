from dataclasses import dataclass
from typing import Optional

from . import config


@dataclass
class Signal:
    ticker: str          # e.g. "IDX:BBCA"
    name: str             # nama perusahaan
    close: float
    change: float         # persen perubahan harian
    trend: str             # "UP" (di atas semua MA) / "DOWN" (di bawah semua MA) / "MIXED"
    nearest_ma: int
    nearest_dist_pct: float
    category: str          # ENTRY / HOLD / OVEREXTENDED / WATCH / AVOID / AVOID_FAR / NEUTRAL


def classify(row) -> Optional[Signal]:
    close = row.get("close")
    if not close or close <= 0:
        return None

    mas = {}
    for p in config.MA_PERIODS:
        v = row.get(f"SMA{p}")
        if v and v > 0:
            mas[p] = v

    # Butuh semua periode MA lengkap (skip saham baru IPO / data belum cukup)
    if len(mas) < len(config.MA_PERIODS):
        return None

    above = [p for p, v in mas.items() if close > v]
    below = [p for p, v in mas.items() if close <= v]
    distances = {p: abs(close - v) / v * 100 for p, v in mas.items()}
    nearest_ma = min(distances, key=distances.get)
    nearest_dist = distances[nearest_ma]

    if len(above) == len(mas):
        trend = "UP"
    elif len(below) == len(mas):
        trend = "DOWN"
    else:
        trend = "MIXED"

    is_near = nearest_dist <= config.NEAR_PCT
    is_far = nearest_dist >= config.FAR_PCT

    # Rule 5: hindari saham di bawah semua MA -> selalu AVOID, apapun jaraknya
    if trend == "DOWN":
        category = "AVOID"
    # Rule 3 + 2: di atas semua MA DAN dekat salah satu MA -> entry terbaik
    elif trend == "UP" and is_near:
        category = "ENTRY"
    # Rule 1: di atas semua MA tapi kejauhan -> jangan kejar, tunggu pullback
    elif trend == "UP" and is_far:
        category = "OVEREXTENDED"
    elif trend == "UP":
        category = "HOLD"
    # Trend campuran tapi lagi dekat MA -> layak dipantau, uji support/resistance
    elif trend == "MIXED" and is_near:
        category = "WATCH"
    # Rule 1: trend belum jelas dan kejauhan dari semua MA -> hindari
    elif trend == "MIXED" and is_far:
        category = "AVOID_FAR"
    else:
        category = "NEUTRAL"

    return Signal(
        ticker=row.get("ticker", row.get("name")),
        name=row.get("description") or row.get("name"),
        close=close,
        change=row.get("change") or 0.0,
        trend=trend,
        nearest_ma=nearest_ma,
        nearest_dist_pct=round(nearest_dist, 2),
        category=category,
    )
