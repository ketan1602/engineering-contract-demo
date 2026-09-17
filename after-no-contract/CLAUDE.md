# Project Context

This is an internal agent run management API built with FastAPI and SQLAlchemy.

## Stack
- Python 3.11
- FastAPI for the API layer
- SQLAlchemy ORM with SQLite (dev) / PostgreSQL (prod)
- Pydantic for request/response schemas
- structlog for structured logging
- RabbitMQ (via pika) as the message broker

## Coding preferences
- Follow PEP 8
- Use type hints throughout
- Prefer async where possible
- Keep functions small and focused
- Use descriptive variable names

## Project structure
- `main.py` — FastAPI app entry point
- `routes/` — one file per resource group
- `schemas.py` — Pydantic models
- `orm_models.py` — SQLAlchemy ORM models
- `database.py` — DB engine and session
- `broker.py` — message broker connection

## Testing
- Use pytest
- Test happy path and error cases
