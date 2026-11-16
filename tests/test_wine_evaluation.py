import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from streamlit.testing.v1 import AppTest

import database.settings as settings
from database.db import Database, ResultsStore, SubmissionStore, initialize_sqlite
from utils.constants import AROMAS, DEFAULT_LOTS
from utils.export import legacy_votes_frame, records_frame
from utils.validation import validate_evaluation


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
        evaluation = validate_evaluation(1, WHITE_ANSWERS, DEFAULT_LOTS)
        self.submissions.save(uuid4(), evaluation)

        self.assertTrue(self.store.has_legacy_records())
        original = self.store.legacy_records()
        self.assertEqual([row["section"] for row in original], ["illat", "iz"])
        frame = legacy_votes_frame(original)
        self.assertEqual(frame["section"].tolist(), ["elsodleges"])
        self.assertEqual(frame["wine"].tolist(), [1])
        self.assertEqual(len(self.store.records(None)), 1)
        with patch.object(settings, "DB_PATH", self.path):
            lots = settings.lots_from_settings(settings.load_settings())
        self.assertEqual(lots[1].name, "Próba tétel")

    def test_retry_archiving_and_new_votes(self):
        initialize_sqlite(self.path)
        evaluation = validate_evaluation(1, WHITE_ANSWERS, DEFAULT_LOTS)
        vote_id = uuid4()
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: self.submissions.save(vote_id, evaluation), range(8)))
        self.assertEqual(len(self.store.records(None)), 1)
        self.assertEqual(self.store.archive(1, datetime.now(timezone.utc)), 1)
        self.submissions.save(uuid4(), evaluation)
        self.assertEqual(len(self.store.records(1, active_only=True)), 1)
        self.assertEqual(set(records_frame(self.store.records(1))["Diagram aktív"]), {False, True})

    def test_named_lots_and_historical_lots_after_count_reduction(self):
        raw = {"wine_count": "2", "wine_1_type": "Vörös", "wine_4_name": "Korábbi tétel"}
        public = settings.lots_from_settings(raw)
        self.assertEqual(list(public), [1, 2])
        self.assertEqual(public[1].wine_type, "Vörösbor")
        admin = settings.lots_from_settings(raw, historical=[4])
        self.assertEqual(list(admin), [1, 2, 4])
        self.assertEqual(admin[4].name, "Korábbi tétel")


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(TemporaryDirectory())) / "wine_votes.db"
        self.enterContext(patch.object(settings, "DB_PATH", self.path))
        self.app = AppTest.from_string("from bor_kostolo_design1 import main\nmain()", default_timeout=15)

    def test_logo_only_header_short_aromas_and_conditional_fields(self):
        self.app.run()
        self.assertFalse(self.app.title)
        self.assertTrue(self.app.get("image"))
        self.app.selectbox(key="wine_lot").set_value(1).run()
        self.assertEqual(answer(self.app.multiselect, "aromas").options, list(AROMAS))
        self.assertEqual(answer(self.app.radio, "fragrance").label, "Illatos vagy nem illatos?")
        self.assertFalse({"Tannin", "Alkohol", "Illat intenzitása"}.intersection(r.label for r in self.app.radio))
        answer(self.app.radio, "fragrance").set_value("Illatos").run()
        answer(self.app.radio, "grape").set_value("Irsai Olivér").run()
        answer(self.app.radio, "fragrance").set_value("Nem illatos").run()
        self.assertIsNone(answer(self.app.radio, "grape").value)
        self.app.selectbox(key="wine_lot").set_value(4).run()
        self.assertEqual(answer(self.app.radio, "variety_group").label, "Világfajta vagy Kárpát-medencei?")
        self.assertFalse(any(r.key and r.key.startswith("wine_fragrance_") for r in self.app.radio))

    def test_submission_requires_filled_form_and_saves_one_record(self):
        self.app.run()
        self.app.selectbox(key="wine_lot").set_value(1).run()
        self.app.button(key="wine_submit").click().run()
        self.assertIn("Töltsd ki", self.app.error[0].value)
        answer(self.app.multiselect, "aromas").set_value(WHITE_ANSWERS["aromas"])
        answer(self.app.radio, "technique").set_value("Reduktív")
        answer(self.app.radio, "fragrance").set_value("Illatos").run()
        answer(self.app.radio, "grape").set_value("Irsai Olivér")
        answer(self.app.selectbox, "region").set_value("Tokaji borvidék")
        answer(self.app.radio, "balance").set_value("Egyensúlyos")
        answer(self.app.selectbox, "score").set_value(8).run()
        self.assertFalse(ResultsStore(Database(self.path)).records(None))
        self.app.button(key="wine_submit").click().run()
        self.assertIn("sikeresen rögzítettük", self.app.success[0].value)
        record, = ResultsStore(Database(self.path)).records(None)
        self.assertEqual(record["score"], 8)
        self.assertIsNone(record["variety_group"])

    def test_admin_query_requires_the_exact_password(self):
        self.app.query_params["admin"] = "1"
        self.app.secrets["ADMIN_PASSWORD"] = "test password"
        with patch("components.admin.results_store", wraps=settings.results_store) as store, \
                patch("components.admin.monotonic", side_effect=[1, 4]):
            self.app.run()
            self.app.text_input[0].set_value("testpassword")
            self.app.button[0].click().run()
            self.assertIn("Helytelen jelszó", self.app.error[0].value)
            store.assert_not_called()
            self.app.text_input[0].set_value("test password")
            self.app.button[0].click().run()
            self.assertFalse(self.app.exception)
            self.assertTrue(self.app.metric)
            store.assert_called()
