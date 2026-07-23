from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yfinance as yf

from . import config

SHORT_PERIODS = [5, 10, 20]
MEDIUM_PERIODS = [20, 50]
LONG_PERIODS = [50, 100, 200]

# Fraksi harga BEI (Peraturan II-A): tick size tergantung golongan harga saham.
_TICK_BANDS = [(200, 1), (500, 2), (2000, 5), (5000, 10), (float("inf"), 25)]


def _tick_size(price: float) -> int:
    for upper, tick in _TICK_BANDS:
        if price < upper:
            return tick
    return 25


def round_to_tick(price: float) -> float:
    """Bulatkan ke kelipatan fraksi harga BEI terdekat sesuai golongan harga saham itu sendiri."""
    tick = _tick_size(price)
    return round(price / tick) * tick


@dataclass
class MACall:
    ticker: str
    price: float
    change: float
    ma_values: Dict[int, float]
    ma_above: Dict[int, bool]
    trend_short: str
    trend_medium: str
    trend_long: str
    verdict_emoji: str
    verdict_text: str
    buy_price: float
    buy_note: str
    sell_price: float
    stop_price: float
    buy_vol_pct: Optional[float]
    sell_vol_pct: Optional[float]
    rvol: Optional[float]
    conclusion: str
    reason: str = ""


def _trend(mas: Dict[int, float], price: float, periods: List[int]) -> str:
    vals = [mas.get(p) for p in periods]
    if any(v is None for v in vals):
        return "BELUM"
    bullish_stack = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
    bearish_stack = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
    if price > max(vals) and bullish_stack:
        return "BULLISH"
    if price < min(vals) and bearish_stack:
        return "BEARISH"
    return "BELUM"


def _levels(price: float, mas: Dict[int, float]) -> Tuple[float, str, float, float]:
    below = sorted((v for v in mas.values() if v < price), reverse=True)
    above = sorted(v for v in mas.values() if v > price)

    if below:
        buy_price = below[0]
        buy_note = "support MA terdekat"
    else:
        buy_price = price
        buy_note = "harga sudah di atas semua MA (breakout)"

    # Stop loss ditaruh sedikit di BAWAH MA support yang jadi alasan entry (buy_price itu
    # sendiri) -- bukan "MA lain yang lebih jauh di bawah", supaya SL selaras dengan alasan
    # setup-nya: begitu harga breakdown di bawah MA itu, setup dianggap gagal.
    stop_price = buy_price * (1 - config.SL_BUFFER_PCT / 100)

    # Target 10-20% dari harga beli. Pakai resistance MA riil kalau kebetulan jatuh di
    # rentang itu (lebih presisi secara teknikal), kalau tidak ada pakai target default
    # di tengah rentang.
    min_target = buy_price * (1 + config.MIN_TARGET_PCT / 100)
    max_target = buy_price * (1 + config.MAX_TARGET_PCT / 100)
    target_candidates = sorted(v for v in above if min_target <= v <= max_target)
    sell_price = target_candidates[0] if target_candidates else buy_price * (1 + config.DEFAULT_TARGET_PCT / 100)

    # Bulatkan ke fraksi harga BEI (tick size beda-beda tergantung golongan harga saham,
    # lihat round_to_tick) supaya level yang direkomendasikan valid dipasang di broker.
    buy_price = round_to_tick(buy_price)
    stop_price = round_to_tick(stop_price)
    sell_price = round_to_tick(sell_price)

    # Untuk saham recehan (harga puluhan rupiah), tick 1 bisa "memakan" gap minimal setelah
    # dibulatkan sehingga stop/target kebulat sama dengan buy -- paksa geser minimal 1 tick.
    tick = _tick_size(buy_price)
    if stop_price >= buy_price:
        stop_price = buy_price - tick
    if sell_price <= buy_price:
        sell_price = buy_price + tick

    return buy_price, buy_note, sell_price, stop_price


def _verdict(short: str, medium: str, long_: str) -> Tuple[str, str]:
    labels = [("pendek", short), ("menengah", medium), ("panjang", long_)]
    bullish = [n for n, t in labels if t == "BULLISH"]
    bearish = [n for n, t in labels if t == "BEARISH"]

    if len(bullish) == 3:
        return "🟢", "BULLISH semua timeframe"
    if bearish and not bullish:
        return "🔴", f"BEARISH ({', '.join(bearish)})"
    if bullish:
        return "🟡", f"BULLISH jangka {' & '.join(bullish)} saja"
    return "⚪", "belum ada arah jelas"


def _conclusion(short: str, medium: str, long_: str) -> str:
    if short == "BULLISH":
        first = "Saatnya MASUK untuk jangka pendek, harga sudah di atas susunan MA5-10-20."
    elif short == "BEARISH":
        first = "Hindari dulu jangka pendek, harga masih di bawah susunan MA5-10-20."
    else:
        first = "Jangka pendek belum ada arah jelas."

    if medium == "BULLISH" and long_ == "BULLISH":
        second = "Trend menengah & panjang juga mendukung, layak hold lebih lama."
    else:
        second = "TUNGGU konfirmasi untuk menengah/panjang sebelum menambah posisi besar."

    return f"{first} {second}"


def _volume_split(ticker_display: str, days: int) -> Tuple[Optional[float], Optional[float]]:
    try:
        hist = yf.Ticker(f"{ticker_display}.JK").history(period=f"{days + 5}d")
    except Exception:
        return None, None

    if hist is None or len(hist) < 2:
        return None, None

    closes = hist["Close"].tolist()[-(days + 1):]
    vols = hist["Volume"].tolist()[-(days + 1):]

    buy_vol = 0.0
    sell_vol = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            buy_vol += vols[i]
        elif closes[i] < closes[i - 1]:
            sell_vol += vols[i]
        else:
            buy_vol += vols[i] / 2
            sell_vol += vols[i] / 2

    total = buy_vol + sell_vol
    if total <= 0:
        return None, None
    return round(buy_vol / total * 100), round(sell_vol / total * 100)


def build_call(row, reason: str = "") -> Optional[MACall]:
    price = row.get("close")
    if not price or price <= 0:
        return None

    mas = {}
    for p in config.DETAIL_MA_PERIODS:
        v = row.get(f"SMA{p}")
        if v and v > 0:
            mas[p] = v

    if not mas:
        return None

    ma_above = {p: price > v for p, v in mas.items()}

    trend_short = _trend(mas, price, SHORT_PERIODS)
    trend_medium = _trend(mas, price, MEDIUM_PERIODS)
    trend_long = _trend(mas, price, LONG_PERIODS)
    verdict_emoji, verdict_text = _verdict(trend_short, trend_medium, trend_long)
    buy_price, buy_note, sell_price, stop_price = _levels(price, mas)
    conclusion = _conclusion(trend_short, trend_medium, trend_long)

    ticker_display = str(row.get("ticker", row.get("name", ""))).split(":")[-1]
    buy_vol_pct, sell_vol_pct = _volume_split(ticker_display, config.VOLUME_SPLIT_DAYS)

    rvol = row.get("relative_volume_10d_calc")
    rvol = float(rvol) if rvol else None

    return MACall(
        ticker=row.get("ticker", row.get("name")),
        price=price,
        change=row.get("change") or 0.0,
        ma_values=mas,
        ma_above=ma_above,
        trend_short=trend_short,
        trend_medium=trend_medium,
        trend_long=trend_long,
        verdict_emoji=verdict_emoji,
        verdict_text=verdict_text,
        buy_price=buy_price,
        buy_note=buy_note,
        sell_price=sell_price,
        stop_price=stop_price,
        buy_vol_pct=buy_vol_pct,
        sell_vol_pct=sell_vol_pct,
        rvol=rvol,
        conclusion=conclusion,
        reason=reason,
    )
