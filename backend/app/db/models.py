from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum as SQLEnum, Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ContractStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    FINISHED = "FINISHED"


class Contract(Base):
    __tablename__ = "contracts"
    contract_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    minio_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[ContractStatus] = mapped_column(SQLEnum(ContractStatus), default=ContractStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    findings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
