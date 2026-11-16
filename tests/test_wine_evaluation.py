import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from streamlit.proto.SelectWidgetFilterMode_pb2 import SelectWidgetFilterMode
from streamlit.testing.v1 import AppTest

import database.settings as settings
from database.db import Database, ResultsStore, SubmissionStore, initialize_sqlite
from utils.constants import AROMAS
from utils.export import legacy_votes_frame, records_frame
from utils.validation import InvalidEvaluation, validate_evaluation


WHITE_ANSWERS = {
    "aromas": ["florális", "citrusféle"], "technique": "Reduktív", "fragrance": "Illatos",
    "grape": "Irsai Olivér", "region": "Tokaji borvidék", "balance": "Egyensúlyos", "score": 8,
}


def answer(widgets, field):
    return next(widget for widget in widgets if widget.key and widget.key.startswith(f"wine_{field}_"))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(TemporaryDirectory())) / "wine_votes.db"
        self.store = ResultsStore(Database(self.path))
        self.submissions = SubmissionStore(self.store.db)

    def test_original_database_is_readable_without_mutating_old_records(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executescript("""CREATE TABLE votes (
                id INTEGER PRIMARY KEY, participant TEXT, section TEXT, question TEXT, option TEXT, created_at TEXT
            );
            INSERT INTO votes VALUES (1, 'old-user', 'illat', 'elsodleges_aromak', 'Florális', '2026-01-01T08:00:00');
            INSERT INTO votes VALUES (2, 'old-user', 'iz', 'elsodleges_aromak', 'Florális', '2026-01-01T08:00:00');
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO settings VALUES ('wine_1_type', 'Fehér');
            INSERT INTO settings VALUES ('wine_1_name', 'Próba tétel');
            """)
        initialize_sqlite(self.path)
        evaluation = validate_evaluation(1, WHITE_ANSWERS)
        self.submissions.save(uuid4(), evaluation)

        self.assertTrue(self.store.has_legacy_records())
        original = self.store.legacy_records()
        self.assertEqual([row["section"] for row in original], ["illat", "iz"])
        frame = legacy_votes_frame(original)
        self.assertEqual(frame["section"].tolist(), ["elsodleges"])
        self.assertEqual(frame["wine"].tolist(), [1])
        self.assertEqual(len(self.store.records(None)), 1)
        with closing(sqlite3.connect(self.path)) as conn:
            name = conn.execute("SELECT value FROM settings WHERE key = 'wine_1_name'").fetchone()[0]
        self.assertEqual(name, "Próba tétel")

    def test_retry_archiving_and_new_votes(self):
        initialize_sqlite(self.path)
        evaluation = validate_evaluation(1, WHITE_ANSWERS)
        vote_id = uuid4()
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: self.submissions.save(vote_id, evaluation), range(8)))
        self.assertEqual(len(self.store.records(None)), 1)
        self.assertEqual(self.store.archive(1, datetime.now(timezone.utc)), 1)
        self.submissions.save(uuid4(), evaluation)
        self.assertEqual(len(self.store.records(1, active_only=True)), 1)
        self.assertEqual(set(records_frame(self.store.records(1))["Diagram aktív"]), {False, True})

    def test_historical_lots_remain_queryable_and_new_submissions_use_fixed_lots(self):
        initialize_sqlite(self.path)
        with self.assertRaises(InvalidEvaluation):
            validate_evaluation(6, WHITE_ANSWERS)
        evaluation = validate_evaluation(1, WHITE_ANSWERS)
        self.submissions.save(uuid4(), replace(evaluation, lot=6))
        self.assertEqual(self.store.historical_lot_types(after_lot=5), {6: "Fehérbor"})
        self.assertEqual(len(self.store.records(6)), 1)


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(TemporaryDirectory())) / "wine_votes.db"
        self.enterContext(patch.object(settings, "DB_PATH", self.path))
        self.app = AppTest.from_string("from bor_kostolo_design1 import main\nmain()", default_timeout=15)

    def test_logo_only_header_short_aromas_and_conditional_fields(self):
        self.app.run()
        self.assertFalse(self.app.title)
        self.assertTrue(self.app.get("image"))
        self.assertFalse(any("Adminisztráció" in element.value for element in self.app.markdown))
        self.assertEqual(self.app.selectbox(key="wine_lot").options, [
            "1. tétel (fehérbor)", "2. tétel (fehérbor)", "3. tétel (fehérbor)",
            "4. tétel (vörösbor)", "5. tétel (vörösbor)",
        ])
        self.app.selectbox(key="wine_lot").set_value(1).run()
        self.assertEqual(answer(self.app.multiselect, "aromas").options, list(AROMAS))
        self.assertEqual(answer(self.app.selectbox, "fragrance").label, "Illatos vagy nem illatos?")
        self.assertFalse(self.app.radio)
        self.assertFalse(self.app.text_input)
        for widget in [*self.app.selectbox, *self.app.multiselect]:
            self.assertEqual(widget.proto.filter_mode, SelectWidgetFilterMode.FILTER_MODE_NONE)
            self.assertFalse(widget.proto.accept_new_options)
        answer(self.app.selectbox, "fragrance").set_value("Illatos").run()
        answer(self.app.selectbox, "grape").set_value("Irsai Olivér").run()
        answer(self.app.selectbox, "fragrance").set_value("Nem illatos").run()
        self.assertIsNone(answer(self.app.selectbox, "grape").value)
        self.app.selectbox(key="wine_lot").set_value(4).run()
        self.assertEqual(answer(self.app.selectbox, "variety_group").label, "Világfajta vagy Kárpát-medencei?")
        self.assertFalse(any(r.key and r.key.startswith("wine_fragrance_") for r in self.app.selectbox))

    def test_submission_requires_filled_form_and_saves_one_record(self):
        self.app.run()
        self.app.selectbox(key="wine_lot").set_value(1).run()
        self.app.button(key="wine_submit").click().run()
        self.assertIn("Töltsd ki", self.app.error[0].value)
        answer(self.app.multiselect, "aromas").set_value(WHITE_ANSWERS["aromas"])
        answer(self.app.selectbox, "technique").set_value("Reduktív")
        answer(self.app.selectbox, "fragrance").set_value("Illatos").run()
        answer(self.app.selectbox, "grape").set_value("Irsai Olivér")
        answer(self.app.selectbox, "region").set_value("Tokaji borvidék")
        answer(self.app.selectbox, "balance").set_value("Egyensúlyos")
        answer(self.app.selectbox, "score").set_value(8).run()
        self.assertFalse(ResultsStore(Database(self.path)).records(None))
        self.app.button(key="wine_submit").click().run()
        self.assertIn("sikeresen rögzítettük", self.app.success[0].value)
        record, = ResultsStore(Database(self.path)).records(None)
        self.assertEqual(record["score"], 8)
        self.assertIsNone(record["variety_group"])

    def test_admin_query_requires_the_exact_password(self):
        self.app.query_params["admin"] = "1"
        with patch("components.admin.results_store", wraps=settings.results_store) as store, \
                patch("components.admin.monotonic", side_effect=[1, 4]):
            self.app.run()
            self.assertFalse(self.app.info)
            self.app.text_input[0].set_value("admin 26")
            self.app.button[0].click().run()
            self.assertIn("Helytelen jelszó", self.app.error[0].value)
            store.assert_not_called()
            self.app.text_input[0].set_value("admin26")
            self.app.button[0].click().run()
            self.assertFalse(self.app.exception)
            self.assertTrue(self.app.metric)
            store.assert_called()

    def test_five_lot_buttons_filter_the_active_count(self):
        initialize_sqlite(self.path)
        store = SubmissionStore(Database(self.path))
        store.save(uuid4(), validate_evaluation(1, WHITE_ANSWERS))
        for score in (6, 8):
            store.save(uuid4(), validate_evaluation(2, {**WHITE_ANSWERS, "score": score}))
        self.app.query_params["admin"] = "1"
        self.app.session_state["admin_authenticated"] = True
        self.app.run()
        self.assertFalse(self.app.exception)
        buttons = [button.label for button in self.app.button if button.key and button.key.startswith("dg-lot-")]
        self.assertEqual(buttons, [f"{number}. tétel" for number in range(1, 6)])
        self.assertEqual([(metric.label, metric.value) for metric in self.app.metric], [("Aktív értékelések", "1")])
        self.app.button(key="dg-lot-2").click().run()
        self.assertEqual([(metric.label, metric.value) for metric in self.app.metric], [("Aktív értékelések", "2")])

        selected, averages = ResultsStore(Database(self.path)).chart_data(2)
        self.assertEqual(sorted(record["score"] for record in selected), [6, 8])
        self.assertEqual(averages, {1: (8.0, 1), 2: (7.0, 2)})
