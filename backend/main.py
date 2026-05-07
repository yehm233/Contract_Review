from __future__ import annotations

import io
import os
import uuid
from datetime import datetime
from enum import Enum

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from minio import Minio
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, JSON, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://root:password@172.27.3.6:3306/contract_review",
)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "172.27.3.6:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "contracts")
MCP_SSE_URL = os.getenv("MCP_SSE_URL", "http://127.0.0.1:8000/sse")


class Base(DeclarativeBase):
    pass


class ContractStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    FINISHED = "FINISHED"


class Contract(Base):
    __tablename__ = "contracts"

    contract_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    minio_url: Mapped[str] = mapped_column(String(512))
    status: Mapped[ContractStatus] = mapped_column(SAEnum(ContractStatus), default=ContractStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), ForeignKey("contracts.contract_id"), index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    findings_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="Contract-Review-Pro Gateway")


def get_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


class OnlyOfficeCallback(BaseModel):
    status: int
    url: str | None = None
    key: str | None = None


class StartReviewPayload(BaseModel):
    contract_id: str


@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.post("/api/onlyoffice/callback")
async def onlyoffice_callback(payload: OnlyOfficeCallback) -> dict:
    if payload.status == 2 and payload.url:
        object_name = f"contracts/{payload.key or str(uuid.uuid4())}.docx"
        async with httpx.AsyncClient(timeout=60) as client:
            file_resp = await client.get(payload.url)
            file_resp.raise_for_status()
        binary_data = file_resp.content

        minio_client = get_minio_client()
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            data=io.BytesIO(binary_data),
            length=len(binary_data),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    return {"error": 0}


@app.post("/api/review/start")
async def start_review(payload: StartReviewPayload, db: AsyncSession = Depends(get_db)) -> dict:
    contract = await db.get(Contract, payload.contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    contract.status = ContractStatus.REVIEWING
    await db.commit()

    prompt_text = f"合同文件：{contract.file_name}，请执行风险扫描。"
    async with httpx.AsyncClient(timeout=30) as client:
        # 简化版：V1.2 使用 mock 回调协议，保持 SSE endpoint 可达
        await client.get(MCP_SSE_URL)
        mcp_result = {
            "findings": [
                {
                    "original_text": prompt_text,
                    "risk_type": "付款条件不明确",
                    "severity": "HIGH",
                    "suggestion": "建议增加分期付款与验收条件。",
                }
            ],
            "total": 1,
        }

    risk_score = 85.0
    review_task = ReviewTask(
        task_id=str(uuid.uuid4()),
        contract_id=contract.contract_id,
        risk_score=risk_score,
        findings_json=mcp_result,
    )
    db.add(review_task)
    contract.status = ContractStatus.FINISHED
    await db.commit()

    return {
        "contract_id": contract.contract_id,
        "status": contract.status.value,
        "risk_score": risk_score,
        "findings": mcp_result["findings"],
    }
