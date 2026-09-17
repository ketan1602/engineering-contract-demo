import json
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import structlog

from database import get_db
from orm_models import RunRecord, RunStatus
from schemas import RunCreate, RunOut
from broker import broker_channel
from settings import MAX_CONCURRENT_RUNS, AVAILABLE_MODELS

logger = structlog.get_logger()

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=List[RunOut])
def list_runs(model_id: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    try:
        query = db.query(RunRecord)
        if model_id:
            query = query.filter(RunRecord.model_id == model_id)
        return query.order_by(RunRecord.created_at.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error("list_runs_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database error")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RunOut)
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
        raise HTTPException(status_code=429, detail=f"Concurrent run limit reached ({MAX_CONCURRENT_RUNS})")

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
                body=json.dumps({"run_id": run_id, "model_id": payload.model_id, "prompt": payload.prompt}),
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


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    except SQLAlchemyError as e:
        logger.error("get_run_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.cancelled and run.status != RunStatus.COMPLETED:
        run.status = RunStatus.CANCELLING
    elif run.status == RunStatus.FAILED and run.retries > 0:
        run.status = f"failed_after_{run.retries}_retries"
    elif run.status == RunStatus.COMPLETED and not run.result:
        run.status = "completed_empty"

    return run


@router.get("/pending", response_model=List[RunOut])
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


@router.put("/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: str, db: Session = Depends(get_db)):
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    except SQLAlchemyError as e:
        logger.error("cancel_run_fetch_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel run in status {run.status}")

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
