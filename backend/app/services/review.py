from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.core.config import MCP_HTTP_BASE
from app.db.models import Contract, ContractStatus, ReviewTask


async def run_review(session, contract_id: str):
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="contract not found")
    contract.status = ContractStatus.REVIEWING
    await session.commit()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{MCP_HTTP_BASE}/tools/risk_assessment_scan", json={"text": contract.file_name})
        resp.raise_for_status()
        payload = resp.json()

    findings = payload.get("findings", [])
    score = float(sum(3 if x.get("severity") == "HIGH" else 2 if x.get("severity") == "MEDIUM" else 1 for x in findings))
    task = ReviewTask(task_id=str(uuid4()), contract_id=contract.contract_id, risk_score=score, findings_json=payload)
    session.add(task)
    contract.status = ContractStatus.FINISHED
    await session.commit()
    return {"contract_id": contract.contract_id, "task_id": task.task_id, "risk_score": score, "findings": findings, "status": contract.status}
