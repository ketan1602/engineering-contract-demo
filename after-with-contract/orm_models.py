from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean
from database import Base


class RunStatus:
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"


class RunRecord(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)
    model_id = Column(String, nullable=False)
    status = Column(String, default=RunStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    retries = Column(Integer, default=0)
    cancelled = Column(Boolean, default=False)


def derive_status(run: RunRecord) -> str:
    """Single authoritative source for display status derivation.

    Eliminates the duplicated if/elif chain that existed in every
    route handler that needed to compute a derived status.
    """
    if run.cancelled and run.status != RunStatus.COMPLETED:
        return RunStatus.CANCELLING
    if run.status == RunStatus.FAILED and run.retries > 0:
        return f"failed_after_{run.retries}_retries"
    if run.status == RunStatus.COMPLETED and not run.result:
        return "completed_empty"
    return run.status
