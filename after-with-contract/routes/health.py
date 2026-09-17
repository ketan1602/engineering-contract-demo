from datetime import datetime
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
