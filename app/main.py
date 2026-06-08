import os
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.telegram import router as telegram_router

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.txt")

app = FastAPI(title="PULS car diagnostic backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pulscar.co",
        "https://www.pulscar.co",
        "http://localhost:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(telegram_router)


def _telegram_webhook_url() -> str:
    explicit = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
    if explicit:
        return explicit

    base_url = os.getenv("PUBLIC_BASE_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if not base_url:
        return ""
    return urljoin(base_url.rstrip("/") + "/", "telegram/webhook")


@app.on_event("startup")
async def configure_telegram_webhook() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    webhook_url = _telegram_webhook_url()
    if not token or not webhook_url:
        return

    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(api_url, json={"url": webhook_url})
    except Exception:
        return
