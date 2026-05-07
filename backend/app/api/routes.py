from uuid import uuid4

from fastapi import APIRouter

from app.db.database import SessionLocal
from app.schemas.review import ReviewStartRequest
from app.services.review import run_review
from app.services.storage import save_onlyoffice_file

router = APIRouter()


@router.post('/api/onlyoffice/callback')
async def onlyoffice_callback(payload: dict):
    if payload.get('status') == 2 and payload.get('url'):
        await save_onlyoffice_file(payload['url'], payload.get('key', str(uuid4())))
    return {'error': 0}


@router.post('/api/review/start')
async def review_start(req: ReviewStartRequest):
    async with SessionLocal() as session:
        return await run_review(session, req.contract_id)
