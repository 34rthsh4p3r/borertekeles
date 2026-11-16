from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st
from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict
from streamlit.errors import StreamlitSecretNotFoundError

from database.db import Database, DatabaseError, ResultsStore, SubmissionStore, initialize_sqlite


DATABASE_NAME = "wine_votes_db"
LOCAL_DB = Path(__file__).resolve().parent.parent / ".local-data" / f"{DATABASE_NAME}.sqlite3"


class DatabaseConfigurationError(DatabaseError):
    pass


def secret(name: str, default=None):
    try:
        return st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default


@st.cache_resource(show_spinner=False)
def local_database(path: Path) -> Database:
    initialize_sqlite(path)
    return Database(local_path=path)


def configured_database(dsn_key: str) -> Database:
    settings = secret("database", {})
    if not isinstance(settings, Mapping):
        raise DatabaseConfigurationError("Hibás adatbázis-beállítás.")
    backend = settings.get("backend", "postgresql")
    if backend == "sqlite":
        url = st.context.url
        if url and urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise DatabaseConfigurationError("A helyi adatbázis csak helyben használható.")
        return local_database(LOCAL_DB)

    dsn = settings.get(dsn_key)
    if backend != "postgresql" or not isinstance(dsn, str) or not dsn.strip():
        raise DatabaseConfigurationError("Az adatbázis nincs beállítva.")
    try:
        database_name = conninfo_to_dict(dsn).get("dbname")
    except ProgrammingError:
        raise DatabaseConfigurationError("A PostgreSQL-kapcsolat beállítása hibás.") from None
    if database_name != DATABASE_NAME:
        raise DatabaseConfigurationError(f"A PostgreSQL-adatbázis neve {DATABASE_NAME} legyen.")
    return Database(dsn=dsn)


def submission_store() -> SubmissionStore:
    return SubmissionStore(configured_database("submit_dsn"))


def results_store() -> ResultsStore:
    return ResultsStore(configured_database("admin_dsn"))
