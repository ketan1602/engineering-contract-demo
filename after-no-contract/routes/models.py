from typing import List

from fastapi import APIRouter, HTTPException
import structlog

from schemas import ModelOut
from settings import AVAILABLE_MODELS, DEFAULT_MODEL

logger = structlog.get_logger()

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=List[ModelOut])
def list_models():
    return list(AVAILABLE_MODELS.values())


@router.get("/{model_id}", response_model=ModelOut)
def get_model(model_id: str):
    model = AVAILABLE_MODELS.get(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return model


@router.get("/default", response_model=ModelOut)
def get_default_model():
    model = AVAILABLE_MODELS.get(DEFAULT_MODEL)
    if not model:
        for m in AVAILABLE_MODELS.values():
            if m["is_default"]:
                return m
        raise HTTPException(status_code=500, detail="No default model configured")
    return model
