from fastapi import FastAPI
from dotenv import load_dotenv
from pathlib import Path

from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.telegram import router as telegram_router

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.txt")

app = FastAPI(title="PULS car diagnostic backend")

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(telegram_router)
