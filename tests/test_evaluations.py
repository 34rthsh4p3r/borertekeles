import csv
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from uuid import uuid4

from openpyxl import load_workbook

from database.db import Database, ResultsStore, SubmissionStore, initialize_sqlite
from utils.aggregates import answer_counts, aroma_counts, score_statistics
from utils.export import COLUMNS, csv_bytes, excel_bytes, export_filename, records_frame
from utils.validation import InvalidEvaluation, validate_evaluation


def white_answers(**overrides):
    return {
        "aromas": ["florális", "citrusféle"], "technique": "Reduktív", "fragrance": "Illatos",
        "grape": "Irsai Olivér", "region": "Tokaji borvidék", "balance": "Egyensúlyos", "score": 8,
        **overrides,
    }


def red_answers(**overrides):
    return white_answers(
        **{"variety_group": "Kárpát-medencei", "grape": "Kékfrankos", "score": 6, **overrides},
    )


class ValidationTests(unittest.TestCase):
    def test_each_lot_sets_wine_type_and_ignores_irrelevant_branch(self):
        for lot in (1, 2, 3):
            result = validate_evaluation(lot, white_answers(variety_group="Világfajta"))
            self.assertEqual(result.wine_type, "Fehérbor")
            self.assertIsNone(result.variety_group)
        for lot in (4, 5):
            result = validate_evaluation(lot, red_answers())
            self.assertEqual(result.wine_type, "Vörösbor")
            self.assertIsNone(result.fragrance)

    def test_rejects_incomplete_and_invalid_answers(self):
        for field, value in (("aromas", []), ("aromas", ["ismeretlen"]), ("technique", None),
                             ("fragrance", {}), ("grape", None), ("region", "Budapest"),
                             ("balance", None), ("score", True), ("score", 11), ("score", "8")):
            with self.subTest(field=field, value=value), self.assertRaises(InvalidEvaluation):
                validate_evaluation(1, white_answers(**{field: value}))
        with self.assertRaises(InvalidEvaluation):
            validate_evaluation(6, white_answers())

    def test_previous_grape_cannot_be_saved_after_switch(self):
        with self.assertRaises(InvalidEvaluation):
            validate_evaluation(1, white_answers(fragrance="Nem illatos"))
        with self.assertRaises(InvalidEvaluation):
            validate_evaluation(4, red_answers(variety_group="Világfajta"))
        result = validate_evaluation(1, white_answers(fragrance="Nem illatos", grape="Furmint"))
        self.assertEqual(result.grape, "Furmint")

    def test_multiple_aromas_are_deduplicated(self):
        evaluation = validate_evaluation(1, white_answers(aromas=["citrusféle", "florális", "citrusféle"]))
        self.assertEqual(evaluation.aromas, ("citrusféle", "florális"))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "test.sqlite3"
        initialize_sqlite(path)
        db = Database(local_path=path)
        self.submit = SubmissionStore(db)
        self.results = ResultsStore(db)

    def add(self, lot=1, score=None, identifier=None):
        answers = white_answers() if lot <= 3 else red_answers()
        if score is not None:
            answers["score"] = score
        identifier = identifier or uuid4()
        self.submit.save(identifier, validate_evaluation(lot, answers))
        return str(identifier)

    def test_parallel_submissions_and_retries(self):
        ids = [uuid4() for _ in range(12)]
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda value: self.add(identifier=value), ids * 2))
        rows = self.results.records(None)
        self.assertEqual(len(rows), 12)
        self.assertEqual({row["id"] for row in rows}, set(results))

    def test_archive_one_lot_then_receive_new_votes(self):
        old_vote = self.add()
        red_vote = self.add(4)
        cutoff = datetime.now(timezone.utc)
        self.assertEqual(self.results.archive(1, cutoff), 1)
        new_vote = self.add(score=9)
        self.assertEqual(self.results.archive(1, cutoff), 0)
        self.assertEqual({row["id"] for row in self.results.records(None, active_only=True)}, {new_vote, red_vote})
        self.assertEqual({row["id"] for row in self.results.records(1)}, {old_vote, new_vote})
        all_rows = {row["id"]: row for row in self.results.records(None)}
        self.assertEqual(len(all_rows), 3)
        self.assertFalse(all_rows[old_vote]["chart_active"])
        self.assertTrue(all_rows[red_vote]["chart_active"])
        self.assertEqual(self.results.dashboard(1)[0], {1: 2})
        self.assertEqual(len(self.results.dashboard(1)[1]), 1)

    def test_archive_cutoff_and_all_lots(self):
        before = self.add()
        cutoff = datetime.now(timezone.utc)
        with self.results.db.connect() as conn:
            conn.execute("UPDATE evaluations SET created_at = '2000-01-01T00:00:00.000000Z' WHERE id = ?", (before,))
        after = self.add(5)
        with self.results.db.connect() as conn:
            conn.execute("UPDATE evaluations SET created_at = '2100-01-01T00:00:00.000000Z' WHERE id = ?", (after,))
        self.assertEqual(self.results.archive(None, cutoff), 1)
        self.assertEqual(self.results.records(None, active_only=True)[0]["id"], after)

    def test_sorting_and_pagination_are_applied_in_the_database(self):
        for score in (7, 6, 9, 8):
            self.add(score=score)
        self.add(4, score=10)
        rows = self.results.records(1, sort="Legmagasabb pontszám elöl", offset=1, limit=2)
        self.assertEqual([row["score"] for row in rows], [8, 7])

    def test_charts_use_active_votes_and_count_each_answer(self):
        self.add(2, score=4)
        self.results.archive(2, datetime.now(timezone.utc))
        self.add(1, score=10)
        self.add(4, score=6)
        counts, active = self.results.dashboard(None)
        self.assertEqual(counts, {1: 1, 2: 1, 4: 1})
        self.assertEqual(aroma_counts(active)["florális"], 2)
        self.assertEqual(aroma_counts(active)["citrusféle"], 2)
        self.assertEqual(aroma_counts(active)["füves"], 0)
        self.assertEqual(answer_counts(active, "fragrance"), {"Illatos": 1})
        self.assertEqual(answer_counts(active, "variety_group"), {"Kárpát-medencei": 1})
        self.assertEqual(answer_counts(active, "technique"), {"Reduktív": 2})
        self.assertEqual(answer_counts(active, "balance"), {"Egyensúlyos": 2})
        self.assertEqual(answer_counts(active, "region"), {"Tokaji borvidék": 2})
        self.assertEqual(answer_counts(active, "grape"), {"Irsai Olivér": 1, "Kékfrankos": 1})
        histogram, average, middle = score_statistics(active)
        self.assertEqual((histogram[6], histogram[10], histogram[4], average, middle), (1, 1, 0, 8, 8))
        self.assertEqual(score_statistics([])[1:], (None, None))

    def test_csv_and_excel_include_archived_votes_and_local_dates(self):
        identifier = self.add(4)
        with self.results.db.connect() as conn:
            conn.execute("UPDATE evaluations SET created_at = '2026-07-01T22:01:02.000000Z' WHERE id = ?",
                         (identifier,))
        self.results.archive(4, datetime(2026, 7, 3, tzinfo=timezone.utc))
        frame = records_frame(self.results.records(4))
        csv_data = csv_bytes(frame)
        self.assertTrue(csv_data.startswith(b"\xef\xbb\xbf"))
        row, = csv.DictReader(StringIO(csv_data.decode("utf-8-sig")), delimiter=";")
        self.assertEqual(tuple(row), COLUMNS)
        self.assertEqual((row["Dátum"], row["Timestamp (HH-MM-SS)"]), ("2026-07-02", "00-01-02"))
        self.assertEqual((row["Bortípus"], row["Szőlőfajta"], row["Diagram aktív"]), ("Vörösbor", "Kékfrankos", "False"))
        self.assertEqual(row["Illatosság"], "")

        workbook = load_workbook(BytesIO(excel_bytes(frame)))
        sheet = workbook["Értékelések"]
        self.assertEqual(tuple(cell.value for cell in sheet[1]), COLUMNS)
        self.assertEqual(sheet["A2"].value, "00-01-02")
        self.assertEqual(sheet["B2"].value.date().isoformat(), "2026-07-02")
        self.assertEqual(sheet["J2"].value, "Kékfrankos")
        self.assertIs(sheet["N2"].value, False)
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, "A1:N2")
        self.assertTrue(sheet["A1"].font.bold)
        self.assertEqual(export_filename(4, "xlsx", datetime(2026, 7, 1, 22, 1, 2, tzinfo=timezone.utc)),
                         "geoterroir_tetel-4_2026-07-02_00-01-02.xlsx")


if __name__ == "__main__":
    unittest.main()
