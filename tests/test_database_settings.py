import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from database import settings
from test_evaluations import white_answers
from utils.validation import validate_evaluation


class DatabaseSettingsTests(unittest.TestCase):
    def test_local_votes_are_saved_in_wine_votes_db(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / settings.LOCAL_DB.name
            with patch.object(settings, "LOCAL_DB", path), \
                    patch.object(settings, "secret", return_value={"backend": "sqlite"}), \
                    patch.object(settings.st, "context", SimpleNamespace(url="http://localhost:8501")):
                identifier = uuid4()
                settings.submission_store().save(identifier, validate_evaluation(1, white_answers()))
                self.assertEqual(path.name, "wine_votes_db.sqlite3")
                self.assertTrue(path.is_file())
                record, = settings.results_store().records(None)
                self.assertEqual(record["id"], str(identifier))

    def test_cloud_uses_the_requested_postgresql_database(self):
        for database in ("wine_votes_db", "postgres"):
            dsn = f"postgresql://example.test/{database}"
            with self.subTest(database=database), patch.object(settings, "secret", return_value={"submit_dsn": dsn}):
                if database == "wine_votes_db":
                    self.assertEqual(settings.submission_store().db.dsn, dsn)
                else:
                    with self.assertRaises(settings.DatabaseConfigurationError):
                        settings.submission_store()

    def test_missing_database_and_cloud_sqlite_are_detected(self):
        context = SimpleNamespace(url="https://example.streamlit.app/")
        for config in ({}, {"backend": "sqlite"}):
            with self.subTest(config=config), patch.object(settings, "secret", return_value=config), \
                    patch.object(settings.st, "context", context):
                with self.assertRaises(settings.DatabaseConfigurationError):
                    settings.submission_store()
