"""Pydantic domain models — service return types and API response shapes.

These models are DISTINCT from SQLAlchemy ORM models (app/db/models.py).
They are used as service return values and FastAPI response_model arguments.
hashed_password and other internal fields are intentionally excluded.
"""
