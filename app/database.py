from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns(bind=None) -> list[str]:
    """Additive schema sync: add any model column missing from an existing table (ALTER TABLE ... ADD COLUMN).
    Covers the common upgrade case without a migration tool. Never drops or alters existing columns."""
    from sqlalchemy import inspect, text
    bind = bind or engine
    insp = inspect(bind)
    added: list[str] = []
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=bind.dialect)}"
                default = col.default.arg if col.default is not None and not callable(getattr(col.default, "arg", None)) else None
                if default is not None:
                    ddl += " DEFAULT " + (f"'{default}'" if isinstance(default, str) else ("1" if default is True else "0" if default is False else str(default)))
                conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
    return added
