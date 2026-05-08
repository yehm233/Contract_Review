import logging
from uuid import uuid4

from fastapi import APIRouter

from app.db.database import SessionLocal
from app.schemas.review import ReviewStartRequest
from app.services.review import run_review
from app.services.storage import save_onlyoffice_file

logger = logging.getLogger("app.routes")

router = APIRouter()


@router.post("/api/onlyoffice/callback")
async def onlyoffice_callback(payload: dict):
    status = payload.get("status")
    url = payload.get("url")
    key = payload.get("key", str(uuid4()))
    logger.info("OnlyOffice callback | status=%s key=%s", status, key)
    if status == 2 and url:
        try:
            result = await save_onlyoffice_file(url, key)
            logger.info("OnlyOffice file saved | %s", result)
        except Exception:
            logger.exception("Failed to save OnlyOffice file | key=%s", key)
    return {"error": 0}


@router.post("/api/review/start")
async def review_start(req: ReviewStartRequest):
    logger.info("Review start | contract_id=%s", req.contract_id)
    async with SessionLocal() as session:
        return await run_review(session, req.contract_id, req.contract_text)
