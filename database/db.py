import json
import logging
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

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
    path: Path

    @contextmanager
    def connect(self, *, snapshot: bool = False):
        try:
            with closing(sqlite3.connect(self.path, timeout=8)) as conn, conn:
                conn.row_factory = sqlite3.Row
                conn.create_function("geoterroir_utc_now", 0, lambda: sqlite_timestamp(datetime.now(timezone.utc)))
                if snapshot:
                    conn.execute("BEGIN")
                yield conn
        except sqlite3.Error as exc:
            LOGGER.warning("Adatbázisművelet sikertelen (%s).", getattr(exc, "sqlite_errorname", type(exc).__name__))
            raise DatabaseError("Az adatbázisművelet sikertelen.") from None


def decode_rows(rows) -> list[dict]:
    records = [dict(row) for row in rows]
    for record in records:
        record["aromas"] = json.loads(record["aromas"])
        if "created_at" in record:
            record["created_at"] = datetime.fromisoformat(record["created_at"])
            record["chart_active"] = bool(record["chart_active"])
    return records


def initialize_sqlite(path: Path) -> None:
    try:
        schema = Path(__file__).with_name("schema.sqlite.sql").read_text(encoding="utf-8")
    except OSError:
        raise DatabaseError("A helyi adatbázis előkészítése sikertelen.") from None
    with Database(path).connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL").fetchone()
        conn.executescript(schema)


@dataclass(frozen=True)
class SubmissionStore:
    db: Database

    def save(self, submission_id: UUID, evaluation: Evaluation) -> None:
        aromas = json.dumps(evaluation.aromas, ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO evaluations
                    (id, lot, wine_type, aromas, technique, fragrance, variety_group,
                     grape, region, balance, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING""",
                (str(submission_id), evaluation.lot, evaluation.wine_type, aromas, evaluation.technique,
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

    def lot_numbers(self) -> list[int]:
        with self.db.connect() as conn:
            return [row["lot"] for row in conn.execute("SELECT DISTINCT lot FROM evaluations ORDER BY lot")]

    def dashboard(self, lot: int | None) -> tuple[dict[int, int], list[dict]]:
        history_filter, history_params = result_filter(lot, False)
        active_filter, active_params = result_filter(lot, True)
        with self.db.connect(snapshot=True) as conn:
            counts = conn.execute(f"""
                SELECT lot, COUNT(*) AS total FROM evaluations{history_filter} GROUP BY lot
                """, history_params).fetchall()
            rows = conn.execute(f"""
                SELECT lot, wine_type, aromas, technique, fragrance, variety_group, grape, region, balance, score
                FROM evaluations{active_filter}
                """, active_params).fetchall()
        return {row["lot"]: row["total"] for row in counts}, decode_rows(rows)

    def records(self, lot: int | None, *, active_only: bool = False,
                sort: str = "Legújabb elöl", limit: int | None = None, offset: int = 0) -> list[dict]:
        where, params = result_filter(lot, active_only)
        query = f"SELECT * FROM evaluations{where} ORDER BY {SORT_ORDERS[sort]}"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params += (limit, offset)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return decode_rows(rows)

    def archive(self, lot: int | None, cutoff: datetime) -> int:
        where, params = result_filter(lot, True)
        with self.db.connect() as conn:
            return conn.execute(
                f"UPDATE evaluations SET chart_active = FALSE{where} AND created_at <= ?",
                (*params, sqlite_timestamp(cutoff)),
            ).rowcount

    def has_legacy_records(self) -> bool:
        with self.db.connect(snapshot=True) as conn:
            has_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'votes'").fetchone()
            return bool(has_table and conn.execute("SELECT 1 FROM votes LIMIT 1").fetchone())

    def legacy_records(self) -> list[dict]:
        with self.db.connect(snapshot=True) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(votes)")}
            if not columns:
                return []
            wine = "wine" if "wine" in columns else "1 AS wine"
            archived = "archived_at" if "archived_at" in columns else "NULL AS archived_at"
            rows = conn.execute(f"""
                SELECT participant, {wine}, section, question, option, created_at, {archived}
                FROM votes ORDER BY id
                """).fetchall()
        return [dict(row) for row in rows]
