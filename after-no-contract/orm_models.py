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
