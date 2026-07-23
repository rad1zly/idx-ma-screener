# IDX MA Screener

Screener saham IDX berbasis Moving Average, kirim hasil scan harian ke grup Telegram sebagai
Telegram Rich Message (tabel asli, bukan teks monospace) via method `sendRichMessage`
(Bot API 10.1+, fitur baru per Juni 2026). Kalau klien Telegram lawas belum support Rich
Messages, pesan akan tetap terkirim dengan fallback tampilan teks biasa.

## Strategi

Data diambil dari TradingView (via library `tradingview-screener`, sumber data yang sama
dipakai oleh [tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp)),
dengan MA20 / MA50 / MA100 / MA200 harian. Setiap saham dikategorikan:

| Kategori | Arti | Rule |
|---|---|---|
| 🟢 ENTRY WATCHLIST | Di atas **semua** MA, dan sedang dekat (≤3%) salah satu MA | #2 + #3 |
| 🔴 SELL SIGNAL | Kemarin di atas semua MA, hari ini gagal bertahan | #4 |
| 🔵 HOLD | Masih solid di atas semua MA, tapi tidak sedang dekat MA manapun | #3 |
| 🟡 OVEREXTENDED | Di atas semua MA tapi sudah terlalu jauh (≥15%) — jangan kejar | #1 |
| 🟠 WATCH | Trend campuran (di atas sebagian MA), sedang menguji salah satu MA | pantauan |
| ⚫ AVOID | Di bawah semua MA (downtrend), atau trend tidak jelas & jauh dari semua MA | #5 + #1 |

Threshold "dekat"/"jauh", jumlah MA, dan filter likuiditas bisa diubah lewat `.env`
(lihat `.env.example`). Sinyal SELL dihitung dengan membandingkan status hari ini vs
kemarin, disimpan di `data/state.json` — jadi scan harus dijalankan tiap hari bursa
supaya sinyal ini akurat.

Saham dengan turnover harian (`close * volume`) di bawah `IDX_MIN_TURNOVER`
(default Rp 1 miliar) otomatis di-skip untuk menghindari saham tidak likuid.

### AI Top Picks (opsional)

Kalau hasil ENTRY/HOLD/WATCH kebanyakan, isi `MINIMAX_API_KEY` di `.env` — nanti LLM
(MiniMax, lewat endpoint OpenAI-compatible-nya) diminta memilih **3-5 saham terbaik**
dari kandidat yang sudah lolos filter rule-based (kategori ENTRY/HOLD, fallback ke WATCH
kalau kandidatnya kurang dari 3). LLM tidak boleh menyebut saham di luar daftar kandidat
yang dikirim, jadi dia hanya me-ranking/memilih, bukan menghasilkan saham baru.

Kalau `MINIMAX_API_KEY` kosong, section "AI TOP PICKS" otomatis di-skip — sisa screener
tetap jalan normal. Kalau panggilan API gagal (network/limit/dsb), scan tetap lanjut dan
kirim tanpa section itu (tidak bikin seluruh scan gagal).

## Setup

```bash
git clone git@github.com:rad1zly/idx-ma-screener.git
cd idx-ma-screener
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Isi `.env`:
- `TELEGRAM_BOT_TOKEN` — buat bot baru lewat [@BotFather](https://t.me/BotFather), `/newbot`, salin token-nya.
- `TELEGRAM_CHAT_ID` — invite bot ke grup, kirim satu pesan apa saja di grup, lalu buka
  `https://api.telegram.org/bot<TOKEN>/getUpdates` di browser untuk melihat `chat.id`
  (angkanya negatif untuk grup).
- `TELEGRAM_MESSAGE_THREAD_ID` (opsional) — kalau grupnya pakai mode **Topics**, isi ini
  supaya hasil scan masuk ke topic tertentu, bukan ke General. Cara ambil: buka topic
  tujuan → titik tiga / klik kanan → "Copy Link" → link-nya berbentuk
  `https://t.me/c/xxxxxxxxxx/<message_thread_id>`, angka terakhir itu yang dipakai.

## Menjalankan

```bash
# test tanpa kirim ke Telegram & tanpa menyimpan state
python3 -m idx_screener.main --dry-run

# jalan normal: scan, simpan state, kirim ke Telegram
python3 -m idx_screener.main
```

## Menjadwalkan scan harian

Screener ini murni script sekali-jalan (bukan proses yang harus terus hidup), jadi
**cukup dijadwalkan lewat cron / scheduler**, tidak perlu bikin Telegram bot yang polling
24 jam. Bot Telegram model polling/webhook baru dibutuhkan kalau nanti mau ada
command interaktif dari user di grup (mis. `/scan BBCA` on-demand) — untuk kebutuhan
sekarang (broadcast hasil scan sekali sehari) itu over-engineering.

Jadwalkan setelah bursa IDX tutup, misalnya jam 16:15 WIB (Senin–Jumat):

```cron
15 16 * * 1-5 cd /path/to/idx-ma-screener && .venv/bin/python3 -m idx_screener.main >> logs/screener.log 2>&1
```

Kalau kamu sudah pakai automation sendiri (openclaw dsb.), tinggal arahkan cron/task
runner-nya untuk menjalankan perintah yang sama di atas — script ini tidak butuh
proses lain yang nyala terus, jadi tinggal dicolok ke scheduler apa pun yang kamu pakai.

## Catatan

- Bukan rekomendasi investasi. Gunakan sebagai alat bantu screening, bukan sinyal beli/jual otomatis.
- `data/state.json` jangan dihapus kalau ingin sinyal SELL tetap akurat hari ke hari.
