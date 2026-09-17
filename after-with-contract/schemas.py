from datetime import datetime
from typing import Optional
from pydantic import BaseModel, validator


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
