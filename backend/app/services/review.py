from uuid import uuid4

from fastapi import HTTPException

from app.core.config import REVIEW_WORKFLOW_MODE
from app.db.models import Contract, ContractStatus, ReviewTask
from app.services.langchain_review import LangChainReviewWorkflow, LangChainWorkflowUnavailable


langchain_workflow = LangChainReviewWorkflow()


async def run_review(session, contract_id: str, contract_text: str | None = None):
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="contract not found")
    contract.status = ContractStatus.REVIEWING
    await session.commit()

    source_text = (contract_text or "").strip() or contract.file_name
    payload = await _run_review_workflow(source_text)

    findings = payload.get("findings", [])
    score = float(sum(3 if x.get("severity") == "HIGH" else 2 if x.get("severity") == "MEDIUM" else 1 for x in findings))
    task = ReviewTask(task_id=str(uuid4()), contract_id=contract.contract_id, risk_score=score, findings_json=payload)
    session.add(task)
    contract.status = ContractStatus.FINISHED
    await session.commit()
    return {
        "contract_id": contract.contract_id,
        "task_id": task.task_id,
        "risk_score": score,
        "findings": findings,
        "entities": payload.get("entities", {}),
        "summary": payload.get("summary", {}),
        "workflow": payload.get("workflow", {"mode": REVIEW_WORKFLOW_MODE}),
        "messages": payload.get("messages", []),
        "status": contract.status,
    }


async def _run_review_workflow(source_text: str) -> dict:
    if REVIEW_WORKFLOW_MODE == "langchain":
        try:
            return await langchain_workflow.review(source_text)
        except LangChainWorkflowUnavailable as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    if REVIEW_WORKFLOW_MODE in {"compat_http", "compat_direct"}:
        try:
            return await langchain_workflow.review_direct(source_text)
        except LangChainWorkflowUnavailable as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=f"unsupported REVIEW_WORKFLOW_MODE: {REVIEW_WORKFLOW_MODE}")
