from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import structlog

from database import get_db
from orm_models import RunRecord, RunStatus
from schemas import RunOut

logger = structlog.get_logger()

router = APIRouter(prefix="/results", tags=["results"])


@router.get("", response_model=List[RunOut])
def list_results(model_id: Optional[str] = None, limit: int = 20, db: Session = Depends(get_db)):
    try:
        query = db.query(RunRecord).filter(RunRecord.status == RunStatus.COMPLETED)
        if model_id:
            query = query.filter(RunRecord.model_id == model_id)
        return query.order_by(RunRecord.updated_at.desc()).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error("list_results_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/{run_id}", response_model=RunOut)
def get_result(run_id: str, db: Session = Depends(get_db)):
    try:
        run = db.query(RunRecord).filter(RunRecord.id == run_id).first()
    except SQLAlchemyError as e:
        logger.error("get_result_failed", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="Database error")

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status != RunStatus.COMPLETED:
        # Duplicate of the status logic in runs.py — already drifted slightly:
        # runs.py also handles "completed_empty"; this version does not.
        if run.cancelled and run.status != RunStatus.COMPLETED:
            display = RunStatus.CANCELLING
        elif run.status == RunStatus.FAILED and run.retries > 0:
            display = f"failed_after_{run.retries}_retries"
        else:
            display = run.status
        raise HTTPException(status_code=404, detail=f"Result not available — run is {display}")

    logger.info("result_fetched", run_id=run_id, model_id=run.model_id)
    return run
