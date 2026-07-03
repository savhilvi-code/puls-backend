from fastapi import APIRouter, HTTPException

from app.schemas.parser import DiagnosticRequest
from app.services.parser_service import ParserUnavailableError, parse_diagnostic

router = APIRouter(tags=["parser"])


@router.post("/search")
async def search(payload: DiagnosticRequest):
    try:
        return await parse_diagnostic(payload.model_dump())
    except ParserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/diagnose")
async def diagnose_route(payload: DiagnosticRequest):
    try:
        return await parse_diagnostic(payload.model_dump())
    except ParserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
