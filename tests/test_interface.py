import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from database.db import DatabaseError


def answer(widgets, field):
    return next(widget for widget in widgets if widget.key.startswith(f"wine_{field}_"))


class InterfaceTests(unittest.TestCase):
    def form(self):
        return AppTest.from_string(
            "from components.evaluation import render_evaluation\nrender_evaluation()",
            default_timeout=15,
        ).run()

    def test_switching_branch_and_lot_clears_previous_answers(self):
        app = self.form()
        self.assertFalse(app.exception)
        app.selectbox(key="wine_lot").set_value(1).run()
        answer(app.radio, "fragrance").set_value("Illatos").run()
        answer(app.radio, "grape").set_value("Irsai Olivér").run()
        answer(app.radio, "fragrance").set_value("Nem illatos").run()
        self.assertEqual(answer(app.radio, "grape").label, "Melyik nem illatos fajta lehet?")
        self.assertIsNone(answer(app.radio, "grape").value)
        answer(app.radio, "fragrance").set_value("Illatos").run()
        self.assertIsNone(answer(app.radio, "grape").value)
        app.selectbox(key="wine_lot").set_value(4).run()
        self.assertEqual(answer(app.radio, "variety_group").label, "Világfajta vagy Kárpát-medencei?")
        self.assertFalse(any(radio.key.startswith("wine_fragrance_") for radio in app.radio))
        answer(app.radio, "variety_group").set_value("Világfajta").run()
        answer(app.radio, "grape").set_value("Merlot").run()
        answer(app.radio, "variety_group").set_value("Kárpát-medencei").run()
        self.assertEqual(answer(app.radio, "grape").label, "Melyik Kárpát-medencei fajta lehet?")
        self.assertIsNone(answer(app.radio, "grape").value)

    def test_invalid_submission_and_retry_keep_the_same_evaluation_id(self):
        store = Mock()
        store.save.side_effect = [DatabaseError("test"), None]
        with patch("components.evaluation.submission_store", return_value=store), \
                patch("components.evaluation.monotonic", side_effect=[10, 20]):
            app = self.form()
            app.selectbox(key="wine_lot").set_value(1).run()
            app.button(key="wine_submit").click().run()
            self.assertIn("Töltsd ki", app.error[0].value)
            store.save.assert_not_called()

            answer(app.multiselect, "aromas").set_value(["florális"])
            answer(app.radio, "technique").set_value("Reduktív")
            answer(app.radio, "fragrance").set_value("Illatos").run()
            answer(app.radio, "grape").set_value("Irsai Olivér")
            answer(app.selectbox, "region").set_value("Tokaji borvidék")
            answer(app.radio, "balance").set_value("Egyensúlyos")
            answer(app.selectbox, "score").set_value(8)
            app.button(key="wine_submit").click().run()
            self.assertIn("megmaradtak", app.error[0].value)
            self.assertTrue(any("Irsai Olivér" in line.value for line in app.markdown))
            app.button(key="wine_retry").click().run()
            self.assertEqual(store.save.call_count, 2)
            self.assertEqual(*store.save.call_args_list)
            self.assertIn("sikeresen rögzítettük", app.success[0].value)
            app.button[0].click().run()
            self.assertIsNone(app.selectbox(key="wine_lot").value)

    def test_admin_never_reads_database_before_authentication(self):
        app = AppTest.from_string("from components.admin import render_admin\nrender_admin()", default_timeout=15)
        app.secrets["ADMIN_PASSWORD"] = "test-admin-login"
        with patch("components.admin.results_store") as store:
            app.run()
            app.text_input[0].set_value("helytelen")
            app.button[0].click().run()
            self.assertIn("Helytelen jelszó", app.error[0].value)
            self.assertFalse(app.metric)
            self.assertFalse(app.get("download_button"))
            store.assert_not_called()
