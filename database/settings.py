from os import getenv
from pathlib import Path

import streamlit as st

from database.db import Database, ResultsStore, SubmissionStore, initialize_sqlite


DB_PATH = Path(__file__).resolve().parent.parent / "wine_votes.db"


def admin_password() -> str | None:
    try:
        password = st.secrets.get("ADMIN_PASSWORD")
    except FileNotFoundError:
        password = None
    return password if isinstance(password, str) and password else getenv("ADMIN_PASSWORD")


@st.cache_resource(show_spinner=False)
def local_database(path: Path) -> Database:
    initialize_sqlite(path)
    return Database(path)


def submission_store() -> SubmissionStore:
    return SubmissionStore(local_database(DB_PATH))


def results_store() -> ResultsStore:
    return ResultsStore(local_database(DB_PATH))
