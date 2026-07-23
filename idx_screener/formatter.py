import re
from datetime import date
from typing import List, Optional

from . import config
from .detail import MACall
from .rules import Signal

_ESCAPE_RE = re.compile(r"([\\`*_\[\]|~])")


def _esc(text: str) -> str:
    """Escape karakter yang bisa merusak Rich Markdown (terutama '|' di dalam tabel)."""
    return _ESCAPE_RE.sub(r"\\\1", str(text))


def _t(ticker: str) -> str:
    return ticker.split(":")[-1]


def _table(rows: List[List[str]], headers: List[str], aligns: List[str]) -> str:
    if not rows:
        return "_tidak ada_"

    align_marker = {"l": ":---", "r": "---:", "c": ":---:"}
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "|" + "|".join(align_marker[a] for a in aligns) + "|"
    row_lines = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([header_line, sep_line, *row_lines])


def _signal_rows(signals: List[Signal], note_fn) -> List[List[str]]:
    return [
        [f"`{_t(s.ticker)}`", f"{s.close:,.0f}", f"{s.change:+.1f}%", _esc(note_fn(s))]
        for s in signals
    ]


def _fmt_call(c: MACall) -> str:
    lines = [f"> **{_t(c.ticker)}** — Rp{c.price:,.0f} ({c.change:+.1f}%)", ">"]
    if c.reason:
        lines.append(f"> _{_esc(c.reason)}_")
        lines.append(">")

    ma_line = "  ".join(
        f"MA{p}:{'✅' if c.ma_above.get(p) else '❌'}"
        for p in config.DETAIL_MA_PERIODS
        if p in c.ma_above
    )
    above_count = sum(1 for v in c.ma_above.values() if v)
    lines.append(f"> Harga vs MA (di atas {above_count}/{len(c.ma_above)}): {ma_line}")
    lines.append(">")
    lines.append(
        f"> ⚡Pendek(5·10·20): **{c.trend_short}**  "
        f"📊Menengah(20·50): **{c.trend_medium}**  "
        f"⛰️Panjang(50·100·200): **{c.trend_long}**"
    )
    lines.append(f"> {c.verdict_emoji} **{_esc(c.verdict_text)}**")
    lines.append(">")
    lines.append(
        f"> 📥 Beli: `Rp{c.buy_price:,.0f}` ({_esc(c.buy_note)})  "
        f"🎯 Jual: `Rp{c.sell_price:,.0f}`  🛑 Stop: `Rp{c.stop_price:,.0f}`"
    )

    if c.buy_vol_pct is not None:
        rvol_note = f", RVOL {c.rvol:.2f}x" if c.rvol else ""
        lines.append(
            f"> 📦 Volume beli/jual (~{config.VOLUME_SPLIT_DAYS}hr): "
            f"{c.buy_vol_pct:.0f}%/{c.sell_vol_pct:.0f}%{rvol_note}"
        )
    elif c.rvol:
        lines.append(f"> 📦 RVOL: {c.rvol:.2f}x")

    lines.append(">")
    lines.append(f"> 🗣️ {_esc(c.conclusion)}")

    return "\n".join(lines)


def build_message(
    signals: List[Signal],
    sell_signals: List[Signal],
    top_picks: Optional[List[MACall]] = None,
) -> str:
    by_cat = {}
    for s in signals:
        by_cat.setdefault(s.category, []).append(s)

    entry = sorted(by_cat.get("ENTRY", []), key=lambda s: s.nearest_dist_pct)[:15]
    hold = sorted(by_cat.get("HOLD", []), key=lambda s: -s.change)[:10]
    overext = sorted(by_cat.get("OVEREXTENDED", []), key=lambda s: -s.nearest_dist_pct)[:10]
    watch = sorted(by_cat.get("WATCH", []), key=lambda s: s.nearest_dist_pct)[:10]
    avoid = by_cat.get("AVOID", []) + by_cat.get("AVOID_FAR", [])
    sells = sorted(sell_signals, key=lambda s: s.change)[:15]

    headers = ["Kode", "Harga", "%", "Ket"]
    aligns = ["l", "r", "r", "l"]

    sections = [f"# 📈 IDX MA Screener — {date.today().strftime('%d %b %Y')}"]

    if top_picks:
        sections.append(f"## 🏆 Top Picks ({len(top_picks)})")
        sections.append("\n\n".join(_fmt_call(c) for c in top_picks))

    sections.append(f"## 🟢 Entry Watchlist ({len(entry)})")
    sections.append("Dekat MA & di atas semua MA.")
    sections.append(
        _table(
            _signal_rows(entry, lambda s: f"dkt MA{s.nearest_ma} {s.nearest_dist_pct:.1f}%"),
            headers,
            aligns,
        )
    )

    sections.append(f"## 🔴 Sell Signal ({len(sells)})")
    sections.append("Gagal bertahan di atas MA.")
    sections.append(
        _table(
            _signal_rows(sells, lambda s: f"break, trend={s.trend}"),
            headers,
            aligns,
        )
    )

    sections.append(f"## 🔵 Hold ({len(hold)})")
    sections.append("Masih solid di atas semua MA.")
    sections.append(_table(_signal_rows(hold, lambda s: ""), headers, aligns))

    sections.append(f"## 🟡 Overextended ({len(overext)})")
    sections.append("Kejauhan dari MA, jangan dikejar.")
    sections.append(
        _table(
            _signal_rows(overext, lambda s: f"jauh dr MA{s.nearest_ma} {s.nearest_dist_pct:.1f}%"),
            headers,
            aligns,
        )
    )

    if watch:
        sections.append(f"## 🟠 Watch ({len(watch)})")
        sections.append("Trend campuran, sedang menguji salah satu MA.")
        sections.append(
            _table(
                _signal_rows(watch, lambda s: f"dkt MA{s.nearest_ma} {s.nearest_dist_pct:.1f}%"),
                headers,
                aligns,
            )
        )

    sections.append(f"## ⚫ Avoid ({len(avoid)} saham)")
    sections.append("Di bawah semua MA, atau jauh dengan trend tidak jelas.")

    cat_ma_list = ", ".join(f"MA{p}" for p in config.MA_PERIODS)
    detail_ma_list = ", ".join(f"MA{p}" for p in config.DETAIL_MA_PERIODS)
    sections.append(
        f"_Kategori pakai {cat_ma_list} \\| Detail Top Picks pakai {detail_ma_list} "
        f"\\| Near ≤{config.NEAR_PCT:.0f}% \\| Far ≥{config.FAR_PCT:.0f}% "
        f"\\| Min turnover Rp{config.MIN_TURNOVER_IDR:,.0f}_"
    )
    sections.append("_Bukan rekomendasi investasi. DYOR._")

    return "\n\n".join(sections)
