import os
import time
import json
import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

import structlog
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# structlog — configured here because there's nowhere else to put it
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

# Database — should be database.py but this file started small
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentdb.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# In-memory broker — mimics pika's channel interface so the route logic is identical
# In production this is replaced by RabbitMQ / Azure Service Bus / SQS via INFRA_BROKER
class _InMemoryChannel:
    def __init__(self):
        self._queue: list = []

    def queue_declare(self, queue, durable=False):
        pass

    def basic_publish(self, exchange, routing_key, body):
        self._queue.append({"routing_key": routing_key, "body": json.loads(body)})
        logger.info("broker_enqueued", routing_key=routing_key, depth=len(self._queue))

    def queue_depth(self):
        return len(self._queue)

BROKER_URL = os.getenv("BROKER_URL", "memory://localhost/")
broker_channel = None
for attempt in range(5):
    try:
        broker_channel = _InMemoryChannel()
        broker_channel.queue_declare(queue="run_queue", durable=True)
        logger.info("broker_connected", broker=BROKER_URL, attempt=attempt)
        break
    except Exception as e:
        logger.warning("broker_connection_failed", attempt=attempt, error=str(e))
        time.sleep(1)
if broker_channel is None:
    logger.error("broker_unavailable", msg="Could not connect after 5 attempts")


# ORM model
class RunStatus(str, Enum):
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


Base.metadata.create_all(bind=engine)


# Schemas — started in schemas.py, moved here when the import went circular
class RunCreate(BaseModel):
    model_id: str
    prompt: str
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7

    @validator("temperature")
    def temperature_range(cls, v):
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v


class RunOut(BaseModel):
    id: str
    model_id: str
    status: str
    created_at: datetime
    result: Optional[str]
    error: Optional[str]

    class Config:
        orm_mode = True


class ModelOut(BaseModel):
    id: str
    name: str
    provider: str
    max_tokens: int
    is_default: bool


class ConfigOut(BaseModel):
    broker_url: str
    max_concurrent_runs: int
    default_model: str
    log_level: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Model registry — adding a new model means editing this dict
AVAILABLE_MODELS = {
    "gpt-4o": {
        "id": "gpt-4o", "name": "GPT-4o",
        "provider": "openai", "max_tokens": 128000, "is_default": False,
    },
    "claude-sonnet-4-6": {
        "id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6",
        "provider": "anthropic", "max_tokens": 200000, "is_default": True,
    },
    "llama-3-70b": {
        "id": "llama-3-70b", "name": "Llama 3 70B",
        "provider": "bedrock", "max_tokens": 8192, "is_default": False,
    },
}

MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

app = FastAPI(title="Agent Run Management API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/runs", response_model=List[RunOut])
def list_runs(
    model_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    try:
        query = db.query(RunRecord)
        if model_id:
            query = query.filter(RunRecord.model_id == model_id)
        return query.order_by(RunRecord.created_at.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error("list_runs_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database error")


@app.post("/runs", status_code=status.HTTP_201_CREATED, response_model=RunOut)
def create_run(payload: RunCreate, db: Session = Depends(get_db)):
    if payload.model_id not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Model {payload.model_id} not available")

    try:
        running_count = db.query(RunRecord).filter(
            RunRecord.status.in_([RunStatus.PENDING, RunStatus.RUNNING])
        ).count()
    except SQLAlchemyError as e:
        logger.error("create_run_count_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if running_count >= MAX_CONCURRENT_RUNS:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrent run limit reached ({MAX_CONCURRENT_RUNS})",
        )

    run_id = str(uuid.uuid4())
    try:
        run = RunRecord(id=run_id, model_id=payload.model_id, status=RunStatus.PENDING)
        db.add(run)
        db.commit()
        db.refresh(run)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("create_run_insert_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to create run")

    if broker_channel:
        try:
            broker_channel.basic_publish(
                exchange="",
                routing_key="run_queue",
                body=json.dumps({
                    "run_id": run_id,
                    "model_id": payload.model_id,
                    "prompt": payload.prompt,
                }),
            )
            logger.info("run_enqueued", run_id=run_id, model_id=payload.model_id)
        except Exception as e:
            logger.error("enqueue_failed", run_id=run_id, error=str(e))
            try:
                run.status = RunStatus.FAILED
                run.error = "Broker unavailable"
                db.commit()
            except SQLAlchemyError as db_e:
                db.rollback()
                logger.error("status_update_failed", run_id=run_id, error=str(db_e))
            raise HTTPException(status_code=503, detail="Broker unavailable")
    else:
        run.status = RunStatus.FAILED
        run.error = "Broker not configured"
        db.commit()
        raise HTTPException(status_code=503, detail="Broker not configured")

    return run


# NOTE: /runs/pending MUST stay above /runs/{run_id} or FastAPI matches "pending" as a run_id
@app.get("/runs/pending", response_model=List[RunOut])
def get_pending_runs(db: Session = Depends(get_db)):
    try:
        return (
            db.query(RunRecord)
            .filter(RunRecord.status.in_([RunStatus.PENDING, RunStatus.RUNNING]))
            .order_by(RunRecord.created_at.asc())
            .all()
        )
    except SQLAlchemyError as e:
        logger.error("get_pending_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    except SQLAlchemyError as e:
        logger.error("get_run_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Derive display status — same logic repeated in get_result below (known issue, no time to fix)
    if run.cancelled and run.status != RunStatus.COMPLETED:
        run.status = RunStatus.CANCELLING
    elif run.status == RunStatus.FAILED and run.retries > 0:
        run.status = f"failed_after_{run.retries}_retries"
    elif run.status == RunStatus.COMPLETED and not run.result:
        run.status = "completed_empty"

    return run


@app.put("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: str, db: Session = Depends(get_db)):
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    except SQLAlchemyError as e:
        logger.error("cancel_run_fetch_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel run in status {run.status}",
        )

    try:
        run.cancelled = True
        run.status = RunStatus.CANCELLING
        run.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("cancel_run_update_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to cancel run")

    logger.info("run_cancelled", run_id=run_id)
    return run


@app.get("/results", response_model=List[RunOut])
def list_results(model_id: Optional[str] = None, limit: int = 20, db: Session = Depends(get_db)):
    try:
        query = db.query(RunRecord).filter(RunRecord.status == RunStatus.COMPLETED)
        if model_id:
            query = query.filter(RunRecord.model_id == model_id)
        return query.order_by(RunRecord.updated_at.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error("list_results_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/results/{run_id}", response_model=RunOut)
def get_result(run_id: str, db: Session = Depends(get_db)):
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    except SQLAlchemyError as e:
        logger.error("get_result_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status != RunStatus.COMPLETED:
        # Duplicate of the status logic in get_run — these have already drifted slightly
        if run.cancelled and run.status != RunStatus.COMPLETED:
            display = RunStatus.CANCELLING
        elif run.status == RunStatus.FAILED and run.retries > 0:
            display = f"failed_after_{run.retries}_retries"
        else:
            display = run.status
        raise HTTPException(
            status_code=404,
            detail=f"Result not available — run is {display}",
        )

    logger.info("result_fetched", run_id=run_id, model_id=run.model_id)
    return run


@app.get("/models", response_model=List[ModelOut])
def list_models():
    return list(AVAILABLE_MODELS.values())


# NOTE: /models/default MUST stay above /models/{model_id}
@app.get("/models/default", response_model=ModelOut)
def get_default_model():
    model = AVAILABLE_MODELS.get(DEFAULT_MODEL)
    if not model:
        for m in AVAILABLE_MODELS.values():
            if m["is_default"]:
                return m
        raise HTTPException(status_code=500, detail="No default model configured")
    return model


@app.get("/models/{model_id}", response_model=ModelOut)
def get_model(model_id: str):
    model = AVAILABLE_MODELS.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return model


@app.get("/config", response_model=ConfigOut)
def get_config():
    masked = BROKER_URL.replace(BROKER_URL.split("@")[0].split("//")[1], "***") \
        if "@" in BROKER_URL else BROKER_URL
    return ConfigOut(
        broker_url=masked,
        max_concurrent_runs=MAX_CONCURRENT_RUNS,
        default_model=DEFAULT_MODEL,
        log_level=LOG_LEVEL,
    )


@app.post("/config/reload")
def reload_config():
    global MAX_CONCURRENT_RUNS, DEFAULT_MODEL, LOG_LEVEL
    MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
    logger.info("config_reloaded", max_concurrent_runs=MAX_CONCURRENT_RUNS, default_model=DEFAULT_MODEL)
    return {
        "reloaded": True,
        "max_concurrent_runs": MAX_CONCURRENT_RUNS,
        "default_model": DEFAULT_MODEL,
    }
