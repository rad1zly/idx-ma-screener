import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"

MARKET = "indonesia"
MA_PERIODS = [20, 50, 100, 200]
# Periode tambahan (hanya dipakai untuk breakdown detail AI top picks, bukan kategorisasi bulk)
DETAIL_MA_PERIODS = [5, 10, 20, 50, 100, 200]
# Jumlah hari histori dipakai untuk estimasi volume beli vs jual (heuristik: volume di hari naik vs turun)
VOLUME_SPLIT_DAYS = int(os.getenv("IDX_VOLUME_SPLIT_DAYS", "10"))

# Minimal jumlah MA (dari 6: MA5/10/20/50/100/200) yang berhasil ditembus harga supaya
# saham masuk pool kandidat AI top-picks. Tidak wajib 6/6 — AI yang menilai lebih dalam.
AI_MIN_MA_ABOVE = int(os.getenv("IDX_AI_MIN_MA_ABOVE", "4"))

# Seberapa dekat harga ke MA supaya dianggap "entry" (persen)
NEAR_PCT = float(os.getenv("IDX_NEAR_PCT", "3"))
# Seberapa jauh harga dari MA terdekat supaya dianggap "overextended" (persen)
FAR_PCT = float(os.getenv("IDX_FAR_PCT", "15"))
# Filter likuiditas: minimum nilai transaksi harian (close * volume) dalam Rupiah
MIN_TURNOVER_IDR = float(os.getenv("IDX_MIN_TURNOVER", "1000000000"))

# Stop loss ditaruh sedikit di BAWAH MA support yang jadi alasan entry (bukan MA lain yang
# lebih jauh) -- kalau harga breakdown di bawah MA itu, setup dianggap gagal.
SL_BUFFER_PCT = float(os.getenv("IDX_SL_BUFFER_PCT", "8"))

# Target profit 12-15% dari harga beli. Kalau ada resistance MA riil yang jatuh di rentang
# ini dipakai, kalau tidak ada pakai target default di tengah rentang.
MIN_TARGET_PCT = float(os.getenv("IDX_MIN_TARGET_PCT", "12"))
MAX_TARGET_PCT = float(os.getenv("IDX_MAX_TARGET_PCT", "15"))
DEFAULT_TARGET_PCT = float(os.getenv("IDX_DEFAULT_TARGET_PCT", "13.5"))
# Jumlah saham yang ditarik dari TradingView per scan (IDX ada ~950 saham tercatat)
FETCH_LIMIT = int(os.getenv("IDX_FETCH_LIMIT", "2000"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Opsional: kalau kosong, layer AI top-picks otomatis di-skip
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
