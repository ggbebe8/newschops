from alembic import context
from backend.app.db import engine, Base

with engine.connect() as connection:
    if engine.dialect.name == "postgresql":
        connection.exec_driver_sql("SELECT pg_advisory_lock(7123401)")
        connection.commit()
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
    if engine.dialect.name == "postgresql":
        connection.exec_driver_sql("SELECT pg_advisory_unlock(7123401)")
        connection.commit()
