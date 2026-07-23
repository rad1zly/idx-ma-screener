import sys

import pandas as pd
import yfinance as yf

from . import config, data
from .detail import _levels

MAX_HOLD_DAYS = 60


def _universe(limit: int = 40) -> list:
    df = data.fetch_idx_stocks()
    df = df[(df["close"] > 0) & (df["volume"] > 0)]
    df["turnover"] = df["close"] * df["volume"]
    df = df[df["turnover"] >= config.MIN_TURNOVER_IDR]
    df = df.sort_values("turnover", ascending=False)
    return [t.split(":")[-1] for t in df["ticker"].head(limit)]


def _simulate_ticker(ticker: str, hist: pd.DataFrame) -> list:
    trades = []
    close = hist["Close"]
    smas = {p: close.rolling(p).mean() for p in config.DETAIL_MA_PERIODS}

    in_position = False
    entry_idx = None
    buy_price = stop_price = sell_price = None

    n = len(hist)
    for i in range(max(config.DETAIL_MA_PERIODS), n):
        price = close.iloc[i]
        if pd.isna(price):
            continue

        mas = {}
        ok = True
        for p in config.DETAIL_MA_PERIODS:
            v = smas[p].iloc[i]
            if pd.isna(v) or v <= 0:
                ok = False
                break
            mas[p] = float(v)
        if not ok:
            continue

        if in_position:
            days_held = i - entry_idx
            hit_tp = price >= sell_price
            hit_sl = price <= stop_price
            if hit_tp or hit_sl or days_held >= MAX_HOLD_DAYS:
                outcome = "TP" if hit_tp else ("SL" if hit_sl else "TIMEOUT")
                ret_pct = (price - buy_price) / buy_price * 100
                trades.append(
                    {
                        "ticker": ticker,
                        "entry_date": hist.index[entry_idx].date().isoformat(),
                        "exit_date": hist.index[i].date().isoformat(),
                        "outcome": outcome,
                        "buy": buy_price,
                        "stop": stop_price,
                        "target": sell_price,
                        "exit_price": float(price),
                        "return_pct": round(ret_pct, 2),
                        "days_held": days_held,
                    }
                )
                in_position = False
            continue

        above = [p for p, v in mas.items() if price > v]
        if len(above) < config.AI_MIN_MA_ABOVE:
            continue

        distances = {p: abs(price - v) / v * 100 for p, v in mas.items()}
        nearest_dist = min(distances.values())
        if nearest_dist > config.NEAR_PCT:
            continue

        buy_price, _, sell_price, stop_price = _levels(float(price), mas)
        entry_idx = i
        in_position = True

    return trades


def run_backtest(limit: int = 40, period: str = "2y") -> pd.DataFrame:
    tickers = _universe(limit)
    print(f"Universe: {len(tickers)} saham (paling likuid hari ini): {', '.join(tickers)}")

    yf_tickers = [f"{t}.JK" for t in tickers]
    raw = yf.download(
        yf_tickers, period=period, group_by="ticker", auto_adjust=True, progress=False, threads=True
    )

    all_trades = []
    skipped = []
    for t in tickers:
        try:
            hist = raw[f"{t}.JK"].dropna(how="all")
        except Exception:
            skipped.append(t)
            continue
        if hist.empty or len(hist) < max(config.DETAIL_MA_PERIODS) + 5:
            skipped.append(t)
            continue
        all_trades.extend(_simulate_ticker(t, hist))

    if skipped:
        print(f"Dilewati (data historis tidak cukup): {', '.join(skipped)}")

    if not all_trades:
        print("Tidak ada trade yang tersimulasikan pada periode ini.")
        return pd.DataFrame()

    tdf = pd.DataFrame(all_trades)
    total = len(tdf)
    win = (tdf["outcome"] == "TP").sum()
    loss = (tdf["outcome"] == "SL").sum()
    timeout = (tdf["outcome"] == "TIMEOUT").sum()
    bad = tdf[(tdf["buy"] - tdf["stop"]).abs() < 1e-6]

    avg_win = tdf.loc[tdf["outcome"] == "TP", "return_pct"].mean()
    avg_loss = tdf.loc[tdf["outcome"] == "SL", "return_pct"].mean()
    rr = abs(avg_win / avg_loss) if avg_loss else float("nan")

    print(f"\n=== Hasil backtest ({period}, {total} trade dari {len(tickers) - len(skipped)} saham) ===")
    print(f"TP     : {win:>3} ({win / total * 100:5.1f}%)")
    print(f"SL     : {loss:>3} ({loss / total * 100:5.1f}%)")
    print(f"Timeout: {timeout:>3} ({timeout / total * 100:5.1f}%)")
    print(f"Avg win  (trade TP) : {avg_win:+.2f}%")
    print(f"Avg loss (trade SL) : {avg_loss:+.2f}%")
    print(f"Realized R:R        : {rr:.2f}")
    print(f"Avg return/trade : {tdf['return_pct'].mean():+.2f}%")
    print(f"Avg holding days : {tdf['days_held'].mean():.1f} hari")
    print(f"Median return    : {tdf['return_pct'].median():+.2f}%")
    print(f"Bug check (buy == stop): {len(bad)} trade")

    return tdf


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    p = sys.argv[2] if len(sys.argv) > 2 else "2y"
    run_backtest(limit=n, period=p)
