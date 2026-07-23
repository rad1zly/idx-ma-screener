import json
from datetime import date
from typing import Iterable, List

from . import config
from .rules import Signal


def load_previous() -> dict:
    if config.STATE_FILE.exists():
        return json.loads(config.STATE_FILE.read_text())
    return {}


def save_current(signals: Iterable[Signal]) -> None:
    payload = {
        "date": date.today().isoformat(),
        "trends": {s.ticker: s.trend for s in signals},
    }
    config.STATE_FILE.write_text(json.dumps(payload, indent=2))


def detect_sell_signals(signals: Iterable[Signal], previous: dict) -> List[Signal]:
    """Rule 4: saham yang kemarin UP (di atas semua MA) tapi hari ini gagal bertahan."""
    prev_trends = previous.get("trends", {})
    sells = []
    for s in signals:
        if prev_trends.get(s.ticker) == "UP" and s.trend != "UP":
            sells.append(s)
    return sells
