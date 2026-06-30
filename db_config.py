import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "11082006")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "horta_comunitaria")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


def get_engine(echo: bool = False):
    """Cria e retorna a engine do SQLAlchemy usada por toda a aplicação."""
    return create_engine(DATABASE_URL, echo=echo, future=True)