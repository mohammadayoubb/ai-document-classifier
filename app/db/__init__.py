"""Database layer — ORM models, session factory, and Alembic migrations.

ORM models (app/db/models.py) are imported EXCLUSIVELY by app/repositories/.
Never import ORM models in routes, services, or domain modules.
"""
