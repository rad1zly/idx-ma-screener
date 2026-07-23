import requests

from . import config


def _chunks(text: str, size: int = 30000):
    """Split by blank-line-separated blocks (section demi section) supaya markdown tidak terpotong."""
    blocks = text.split("\n\n")
    buf = ""
    for block in blocks:
        candidate = f"{buf}\n\n{block}" if buf else block
        if len(candidate) > size and buf:
            yield buf
            buf = block
        else:
            buf = candidate
    if buf:
        yield buf


def send_message(text: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum di-set. Isi file .env terlebih dahulu."
        )

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendRichMessage"
    for chunk in _chunks(text):
        resp = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "rich_message": {"markdown": chunk},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram sendRichMessage gagal: {data}")
