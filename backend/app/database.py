import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Este proyecto funciona exclusivamente con PostgreSQL: no existe ningún
# respaldo en SQLite. Si falta la conexión, el proceso no debe arrancar.
POSTGRESQL_PREFIXES = ("postgresql://", "postgresql+")


def load_database_url() -> str:
    """Valida `DATABASE_URL` y devuelve la conexión a PostgreSQL."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL no está definida. Este proyecto usa únicamente PostgreSQL: "
            "copia .env.example a .env, completa la conexión y vuelve a iniciar."
        )
    if not url.startswith(POSTGRESQL_PREFIXES):
        scheme = url.split(":", 1)[0]
        raise RuntimeError(
            f"DATABASE_URL debe apuntar a PostgreSQL (postgresql+psycopg://...). Recibido: {scheme}://"
        )
    return url


DATABASE_URL = load_database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
