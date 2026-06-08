from fastapi import APIRouter

from app.schemas.parser import DiagnosticRequest
from app.services.parser_engine import diagnose

router = APIRouter(tags=["parser"])


@router.post("/search")
async def search(payload: DiagnosticRequest):
    return await diagnose(payload)


@router.post("/diagnose")
async def diagnose_route(payload: DiagnosticRequest):
    return await diagnose(payload)
