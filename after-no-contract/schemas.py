from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict


class RunCreate(BaseModel):
    model_id: str
    prompt: str
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7

    @field_validator("temperature")
    @classmethod
    def temperature_range(cls, v):
        if v is not None and not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_id: str
    status: str
    created_at: datetime
    result: Optional[str] = None
    error: Optional[str] = None


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
