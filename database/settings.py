from collections.abc import Iterable, Mapping
from os import getenv
from pathlib import Path

import streamlit as st

from database.db import Database, ResultsStore, SubmissionStore, initialize_sqlite
from utils.constants import DEFAULT_LOTS, MAX_LOTS, WINE_TYPES, WineLot


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


def load_settings() -> dict[str, str]:
    with local_database(DB_PATH).connect() as conn:
        return dict(conn.execute("SELECT key, value FROM settings").fetchall())


def save_settings(changes: Mapping[str, object]) -> None:
    with local_database(DB_PATH).connect() as conn:
        conn.executemany(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [(key, str(value)) for key, value in changes.items()],
        )


def lots_from_settings(settings: Mapping[str, str], historical: Iterable[int] = ()) -> dict[int, WineLot]:
    count = len(DEFAULT_LOTS)
    try:
        count = max(1, min(int(settings.get("wine_count", count)), MAX_LOTS))
    except (TypeError, ValueError):
        pass
    numbers = sorted(set(range(1, count + 1)).union(historical))
    lots = {}
    for number in numbers:
        default = DEFAULT_LOTS.get(number, WineLot(f"{number}. tétel", WINE_TYPES[0]))
        name = settings.get(f"wine_{number}_name") or default.name
        wine_type = settings.get(f"wine_{number}_type", default.wine_type)
        wine_type = {"Fehér": "Fehérbor", "Vörös": "Vörösbor"}.get(wine_type, wine_type)
        lots[number] = WineLot(name, wine_type if wine_type in WINE_TYPES else default.wine_type)
    return lots
