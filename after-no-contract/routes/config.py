import os

from fastapi import APIRouter
import structlog

from schemas import ConfigOut
from broker import BROKER_URL
import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ConfigOut)
def get_config():
    masked = BROKER_URL.replace(BROKER_URL.split("@")[0].split("//")[1], "***") \
        if "@" in BROKER_URL else BROKER_URL
    return ConfigOut(
        broker_url=masked,
        max_concurrent_runs=settings.MAX_CONCURRENT_RUNS,
        default_model=settings.DEFAULT_MODEL,
        log_level=settings.LOG_LEVEL,
    )


@router.post("/reload")
def reload_config():
    settings.MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))
    settings.DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
    settings.LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
    logger.info("config_reloaded",
                max_concurrent_runs=settings.MAX_CONCURRENT_RUNS,
                default_model=settings.DEFAULT_MODEL)
    return {"reloaded": True, "max_concurrent_runs": settings.MAX_CONCURRENT_RUNS,
            "default_model": settings.DEFAULT_MODEL}
