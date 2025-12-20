import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# En Render (o producción) es común definir DATABASE_URL.
# Si no existe, usamos SQLite local (simple.db en la misma carpeta).
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./simple.db")

# Render/Postgres a veces entrega postgres://, pero SQLAlchemy espera postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.environ.get("SQL_ECHO", "0") == "1",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
