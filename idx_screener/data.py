import pandas as pd
from tradingview_screener import stocks

from . import config

SMA_COLUMNS = [f"SMA{p}" for p in config.DETAIL_MA_PERIODS]


def fetch_idx_stocks() -> pd.DataFrame:
    """Ambil snapshot harian seluruh saham IDX beserta SMA5/10/20/50/100/200 + RVOL dari TradingView."""
    columns = [
        "name",
        "description",
        "close",
        "volume",
        "change",
        "relative_volume_10d_calc",
        *SMA_COLUMNS,
    ]
    _, df = (
        stocks(config.MARKET)
        .select(*columns)
        .limit(config.FETCH_LIMIT)
        .get_scanner_data()
    )
    return df
