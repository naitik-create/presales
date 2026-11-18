import os

from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  registers all tables
from app.config import get_settings
from app.db import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = os.environ.get("MIGRATE_DATABASE_URL") or get_settings().DATABASE_URL
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
