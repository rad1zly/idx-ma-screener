import sys

from . import config, data, detail, formatter, llm, rules, state, telegram


def run(send: bool = True, dry_run: bool = False) -> str:
    df = data.fetch_idx_stocks()

    df = df[(df["close"] > 0) & (df["volume"] > 0)]
    df["turnover"] = df["close"] * df["volume"]
    df = df[df["turnover"] >= config.MIN_TURNOVER_IDR]

    rows_by_ticker = {row["ticker"].split(":")[-1]: row for _, row in df.iterrows()}

    signals = []
    for _, row in df.iterrows():
        sig = rules.classify(row)
        if sig:
            signals.append(sig)

    previous = state.load_previous()
    sell_signals = state.detect_sell_signals(signals, previous)

    picks = llm.pick_top_stocks(df)
    top_calls = []
    if picks:
        for ticker, reason in picks:
            row = rows_by_ticker.get(ticker)
            if row is None:
                continue
            call = detail.build_call(row, reason)
            if call:
                top_calls.append(call)

    message = formatter.build_message(signals, sell_signals, top_calls)

    if not dry_run:
        state.save_current(signals)

    print(message)

    if send and not dry_run:
        telegram.send_message(message)

    return message


if __name__ == "__main__":
    is_dry_run = "--dry-run" in sys.argv
    is_no_send = "--no-send" in sys.argv or is_dry_run
    run(send=not is_no_send, dry_run=is_dry_run)
