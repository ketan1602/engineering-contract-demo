import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from routes import runs, results, models, config

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Run Management API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(runs.router)
app.include_router(results.router)
app.include_router(models.router)
app.include_router(config.router)
