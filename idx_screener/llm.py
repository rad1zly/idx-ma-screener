import json
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf
from tradingview_screener import stocks

from . import config

SYSTEM_PROMPT = (
    "Kamu adalah analis screening saham IDX yang menggabungkan tiga sudut pandang: teknikal "
    "(Moving Average), fundamental, dan narasi/berita terkini. Strategi MA yang dipakai:\n"
    "1. Hindari saham yang jauh dari MA (overextended).\n"
    "2. Entry saham yang harganya dekat dengan salah satu MA (potensi support/pullback).\n"
    "3. Saham yang berada di atas lebih banyak MA lebih disukai, tapi TIDAK WAJIB di atas semua MA — "
    "6/6 tentu lebih kuat dari 4/6, tapi 4/6 atau 5/6 masih layak dipertimbangkan kalau setup-nya bagus.\n"
    "4. Saham yang gagal bertahan di atas MA sebaiknya dihindari/dijual.\n"
    "5. Hindari saham yang berada di bawah semua atau hampir semua MA.\n\n"
    "Selain data MA, tiap kandidat juga dilengkapi data fundamental (PE, PB, ROE, dividend yield, "
    "sektor) dan judul berita terbaru kalau tersedia (banyak saham tidak ada beritanya, itu wajar, "
    "jangan jadikan alasan otomatis untuk skip). Pertimbangkan ketiganya secara seimbang: jangan "
    "cuma pilih berdasarkan teknikal MA saja — valuasi yang terlalu mahal (PE/PB tinggi tanpa ROE "
    "yang sepadan) atau berita negatif (litigasi, penurunan kinerja, dsb) harus mengurangi skor "
    "meskipun setup MA-nya bagus, dan sebaliknya.\n\n"
    "Kamu akan diberi daftar kandidat saham yang sudah lolos filter likuiditas dan minimal jumlah MA "
    "yang berhasil ditembus (lihat kolom di_atas_ma). Kolom `di_bawah_ma` menunjukkan MA mana saja yang "
    "BELUM ditembus harga saat ini. Tugasmu: ANALISA lebih dalam dari rule sederhana itu, lalu pilih 3 "
    "sampai 5 saham TERBAIK dari daftar itu — JANGAN menyebut saham di luar daftar yang diberikan. "
    "Urutkan dari paling menarik, dan alasan yang kamu tulis harus menyinggung minimal satu aspek "
    "non-teknikal (fundamental atau berita) kalau datanya tersedia untuk saham itu. Balas HANYA dengan "
    "JSON array valid, tanpa teks/markdown lain, format persis:\n"
    '[{"ticker": "XXXX", "reason": "alasan singkat maksimal 20 kata, Bahasa Indonesia"}]'
)

FUNDAMENTAL_COLUMNS = [
    "sector",
    "price_earnings_ttm",
    "price_book_fq",
    "dividend_yield_recent",
    "return_on_equity",
    "debt_to_equity",
]

# Jumlah kandidat teratas (secara teknikal) yang diperkaya dengan fundamental + berita.
# Dibatasi supaya fetch berita per-saham (satu request per ticker) tidak membuat scan lambat.
SHORTLIST_SIZE = 25
NEWS_PER_TICKER = 2


def _build_candidates(df: pd.DataFrame) -> List[dict]:
    candidates = []
    for _, row in df.iterrows():
        price = row.get("close")
        if not price or price <= 0:
            continue

        mas = {}
        for p in config.DETAIL_MA_PERIODS:
            v = row.get(f"SMA{p}")
            if v and v > 0:
                mas[p] = v

        if len(mas) < len(config.DETAIL_MA_PERIODS):
            continue  # butuh 6 MA lengkap supaya penilaian AI konsisten

        above = sorted(p for p, v in mas.items() if price > v)
        below = sorted(p for p, v in mas.items() if price <= v)
        if len(above) < config.AI_MIN_MA_ABOVE:
            continue

        distances = {p: abs(price - v) / v * 100 for p, v in mas.items()}
        nearest_ma = min(distances, key=distances.get)

        candidates.append(
            {
                "ticker": row["ticker"].split(":")[-1],
                "close": price,
                "change": row.get("change") or 0.0,
                "above": above,
                "below": below,
                "nearest_ma": nearest_ma,
                "nearest_dist_pct": round(distances[nearest_ma], 2),
            }
        )
    return candidates


def _fetch_fundamentals(tickers: set) -> Dict[str, dict]:
    try:
        _, df = (
            stocks(config.MARKET)
            .select("name", *FUNDAMENTAL_COLUMNS)
            .limit(config.FETCH_LIMIT)
            .get_scanner_data()
        )
    except Exception as e:
        print(f"[llm] gagal ambil data fundamental, dilewati: {e}")
        return {}

    result = {}
    for _, row in df.iterrows():
        t = row["ticker"].split(":")[-1]
        if t in tickers:
            result[t] = row.to_dict()
    return result


def _fetch_news_titles(ticker: str, limit: int = NEWS_PER_TICKER) -> List[str]:
    try:
        items = yf.Ticker(f"{ticker}.JK").news or []
    except Exception:
        return []

    titles = []
    for item in items[:limit]:
        content = item.get("content", item)
        title = content.get("title")
        if title:
            titles.append(title)
    return titles


def _fundamental_str(f: dict) -> str:
    parts = []
    pe = f.get("price_earnings_ttm")
    if pe:
        parts.append(f"PE={pe:.1f}")
    pb = f.get("price_book_fq")
    if pb:
        parts.append(f"PB={pb:.1f}")
    roe = f.get("return_on_equity")
    if roe:
        parts.append(f"ROE={roe:.1f}%")
    div = f.get("dividend_yield_recent")
    if div:
        parts.append(f"Div={div:.1f}%")
    der = f.get("debt_to_equity")
    if der:
        parts.append(f"DER={der:.1f}")
    sector = f.get("sector")
    if sector:
        parts.append(f"sektor={sector}")
    return ", ".join(parts) if parts else "tidak tersedia"


def pick_top_stocks(df: pd.DataFrame) -> Optional[List[Tuple[str, str]]]:
    """Minta MiniMax memilih 3-5 saham terbaik dari kandidat >= AI_MIN_MA_ABOVE/6 MA,
    diperkaya data fundamental + judul berita. None kalau di-skip/gagal."""
    if not config.MINIMAX_API_KEY:
        return None

    candidates = _build_candidates(df)
    if not candidates:
        return None

    candidates.sort(key=lambda c: (-len(c["above"]), c["nearest_dist_pct"]))
    shortlist = candidates[:SHORTLIST_SIZE]

    fundamentals = _fetch_fundamentals({c["ticker"] for c in shortlist})

    lines = []
    for c in shortlist:
        fund_str = _fundamental_str(fundamentals.get(c["ticker"], {}))
        news_titles = _fetch_news_titles(c["ticker"])
        news_str = " || ".join(news_titles) if news_titles else "tidak ada berita terbaru"

        lines.append(
            f"{c['ticker']} | close={c['close']:.0f} | change={c['change']:+.1f}% "
            f"| di_atas_ma={len(c['above'])}/{len(config.DETAIL_MA_PERIODS)} "
            f"| di_bawah_ma={','.join(f'MA{p}' for p in c['below']) or 'tidak ada'} "
            f"| jarak_ke_MA{c['nearest_ma']}={c['nearest_dist_pct']:.1f}% "
            f"| fundamental: {fund_str} | berita: {news_str}"
        )
    user_prompt = "Daftar kandidat:\n" + "\n".join(lines)

    try:
        resp = requests.post(
            f"{config.MINIMAX_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.MINIMAX_API_KEY}"},
            json={
                "model": config.MINIMAX_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[llm] gagal memanggil MiniMax, section AI top-picks di-skip: {e}")
        return None

    # Model reasoning (mis. MiniMax-M3) kadang menyisipkan blok <think>...</think>, dan kadang
    # kurung siku pembuka "[" nyangkut di dalam blok itu sehingga array JSON di luar think jadi
    # tidak lengkap. Daripada parse array utuh, ekstrak tiap object {...} satu-satu -> lebih tahan
    # terhadap kurung yang tidak seimbang / teks tambahan di luar JSON.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    objects = re.findall(r"\{[^{}]*\}", content)

    picks = []
    for obj in objects:
        try:
            picks.append(json.loads(obj))
        except json.JSONDecodeError:
            continue

    if not picks:
        print(f"[llm] tidak ada objek JSON valid dari MiniMax, di-skip. Isi: {content[:200]!r}")
        return None

    valid_tickers = {c["ticker"] for c in shortlist}
    result = []
    for p in picks:
        ticker = str(p.get("ticker", "")).upper().strip()
        if ticker in valid_tickers:
            result.append((ticker, str(p.get("reason", "")).strip()))

    return result[:5] or None
