import json
import logging
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from utils.validation import Evaluation


LOGGER = logging.getLogger(__name__)
SORT_ORDERS = {
    "Legújabb elöl": "created_at DESC, id DESC",
    "Legrégebbi elöl": "created_at ASC, id ASC",
    "Legmagasabb pontszám elöl": "score DESC, created_at DESC, id DESC",
    "Legalacsonyabb pontszám elöl": "score ASC, created_at DESC, id DESC",
}


class DatabaseError(RuntimeError):
    pass


def sqlite_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class Database:
    dsn: str = field(default="", repr=False)
    local_path: Path | None = None

    @property
    def table(self) -> str:
        return "evaluations" if self.local_path is not None else "geoterroir.evaluations"

    @contextmanager
    def connect(self, *, snapshot: bool = False):
        try:
            if self.local_path is not None:
                with closing(sqlite3.connect(self.local_path, timeout=8)) as conn, conn:
                    conn.row_factory = sqlite3.Row
                    conn.create_function("geoterroir_utc_now", 0, lambda: sqlite_timestamp(datetime.now(timezone.utc)))
                    if snapshot:
                        conn.execute("BEGIN")
                    yield conn
            else:
                with psycopg.connect(self.dsn, connect_timeout=6, row_factory=dict_row) as conn:
                    if snapshot:
                        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    conn.execute("SET LOCAL statement_timeout = '25s'")
                    yield conn
        except (sqlite3.Error, psycopg.Error) as exc:
            LOGGER.warning("Adatbázisművelet sikertelen (%s, SQLSTATE=%s).", type(exc).__name__,
                           getattr(exc, "sqlstate", None))
            raise DatabaseError("Az adatbázisművelet sikertelen.") from None

    def execute(self, conn, query: str, params: tuple = ()):
        if self.local_path is None:
            query = query.replace("?", "%s")
        return conn.execute(query, params)

    def decode_rows(self, rows) -> list[dict]:
        records = [dict(row) for row in rows]
        if self.local_path is not None:
            for record in records:
                record["aromas"] = json.loads(record["aromas"])
                if "created_at" in record:
                    record["created_at"] = datetime.fromisoformat(record["created_at"])
                    record["chart_active"] = bool(record["chart_active"])
        return records


def initialize_sqlite(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        schema = Path(__file__).with_name("schema.sqlite.sql").read_text(encoding="utf-8")
    except OSError:
        raise DatabaseError("A helyi adatbázis előkészítése sikertelen.") from None
    with Database(local_path=path).connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL").fetchone()
        conn.executescript(schema)


@dataclass(frozen=True)
class SubmissionStore:
    db: Database

    def save(self, submission_id: UUID, evaluation: Evaluation) -> None:
        if self.db.local_path is not None:
            identifier = str(submission_id)
            aromas = json.dumps(evaluation.aromas, ensure_ascii=False)
        else:
            identifier = submission_id
            aromas = Jsonb(evaluation.aromas)

        with self.db.connect() as conn:
            self.db.execute(
                conn,
                f"""INSERT INTO {self.db.table}
                    (id, lot, wine_type, aromas, technique, fragrance, variety_group,
                     grape, region, balance, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (identifier, evaluation.lot, evaluation.wine_type, aromas, evaluation.technique,
                 evaluation.fragrance, evaluation.variety_group, evaluation.grape, evaluation.region,
                 evaluation.balance, evaluation.score),
            )


def result_filter(lot: int | None, active_only: bool) -> tuple[str, tuple]:
    filters = []
    params = ()
    if lot is not None:
        filters.append("lot = ?")
        params = (lot,)
    if active_only:
        filters.append("chart_active = TRUE")
    return (" WHERE " + " AND ".join(filters) if filters else ""), params


@dataclass(frozen=True)
class ResultsStore:
    db: Database

    def current_time(self) -> datetime:
        if self.db.local_path is not None:
            return datetime.now(timezone.utc)
        with self.db.connect() as conn:
            return conn.execute("SELECT clock_timestamp() AS cutoff").fetchone()["cutoff"]

    def dashboard(self, lot: int | None) -> tuple[dict[int, int], list[dict]]:
        history_filter, history_params = result_filter(lot, False)
        active_filter, active_params = result_filter(lot, True)
        with self.db.connect(snapshot=True) as conn:
            counts = self.db.execute(conn, f"""
                SELECT lot, COUNT(*) AS total FROM {self.db.table}{history_filter} GROUP BY lot
                """, history_params).fetchall()
            rows = self.db.execute(conn, f"""
                SELECT lot, aromas, technique, fragrance, variety_group, grape, region, balance, score
                FROM {self.db.table}{active_filter}
                """, active_params).fetchall()
        return {row["lot"]: row["total"] for row in counts}, self.db.decode_rows(rows)

    def records(self, lot: int | None, *, active_only: bool = False,
                sort: str = "Legújabb elöl", limit: int | None = None, offset: int = 0) -> list[dict]:
        where, params = result_filter(lot, active_only)
        query = f"SELECT * FROM {self.db.table}{where} ORDER BY {SORT_ORDERS[sort]}"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params += (limit, offset)
        with self.db.connect(snapshot=True) as conn:
            rows = self.db.execute(conn, query, params).fetchall()
        return self.db.decode_rows(rows)

    def archive(self, lot: int | None, cutoff: datetime) -> int:
        where, params = result_filter(lot, True)
        if self.db.local_path is not None:
            cutoff = sqlite_timestamp(cutoff)
        with self.db.connect() as conn:
            return self.db.execute(
                conn,
                f"UPDATE {self.db.table} SET chart_active = FALSE{where} AND created_at <= ?",
                (*params, cutoff),
            ).rowcount
