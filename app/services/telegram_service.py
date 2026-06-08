import os

import httpx


async def send_telegram_message(*, chat_id: str, text: str) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return {"ok": False, "sent": False}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload)
    return {"ok": response.is_success, "sent": response.is_success}

