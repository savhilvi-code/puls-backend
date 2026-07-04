from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

from app.routers.chat import router as chat_router
from app.routers.history import router as history_router
from app.routers.health import router as health_router
from app.routers.search import router as search_router
from app.routers.vehicles import router as vehicles_router

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
app.include_router(search_router)
app.include_router(history_router)
app.include_router(vehicles_router)
