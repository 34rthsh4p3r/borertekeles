from html import escape
from pathlib import Path
from time import monotonic
from uuid import uuid4

import streamlit as st

from database.db import DatabaseError
from database.settings import DatabaseConfigurationError, submission_store
from utils.constants import (
    AROMAS, AROMA_QUESTION, BALANCES, BALANCE_QUESTION, LOTS, LOT_QUESTION,
    REGIONS, REGION_QUESTION, SCORES, SCORE_QUESTION, TECHNIQUES,
    TECHNIQUE_QUESTION, lot_label, variety_branch,
)
from utils.rate_limit import SUBMISSION_LIMIT
from utils.validation import InvalidEvaluation, validate_evaluation


HEADER_IMAGE = Path(__file__).resolve().parent.parent / "assets" / "GEOTerroir_HUN.jpg"
ANSWER_KEYS = ("aromas", "technique", "fragrance", "variety_group", "grape", "region", "balance", "score")
SUCCESS = "Köszönjük az értékelést! A válaszaidat sikeresen rögzítettük."
SAVE_FAILURE = "A mentést nem sikerült visszaigazolni. A kitöltött válaszaid megmaradtak. Próbáld újra!"
SETUP_REQUIRED = "A mentéshez be kell állítani a wine_votes_db adatbázist. A kitöltött válaszaid megmaradtak."


def clear_grape() -> None:
    st.session_state.wine_grape_revision = st.session_state.get("wine_grape_revision", 0) + 1


def clear_answers() -> None:
    st.session_state.wine_draft_revision = st.session_state.get("wine_draft_revision", 0) + 1


def answer_key(field: str) -> str:
    draft = st.session_state.get("wine_draft_revision", 0)
    # Rerender with a fresh widget identity so that the browser also clears its selection.
    if field == "grape":
        return f"wine_grape_{draft}_{st.session_state.get('wine_grape_revision', 0)}"
    return f"wine_{field}_{draft}"


def restart() -> None:
    clear_answers()
    st.session_state.pop("wine_lot", None)
    st.session_state.pop("wine_submitted", None)


def question_card(name: str):
    return st.container(border=True, key=f"question-{name}")


def single_choice(label: str, options, name: str, **kwargs):
    with question_card(name):
        return st.radio(label, tuple(options), index=None, key=answer_key(name), **kwargs)


def region_choice() -> str | None:
    with question_card("region"):
        return st.selectbox(REGION_QUESTION, REGIONS, index=None, key=answer_key("region"),
                            placeholder="Válassz borvidéket...")


def score_choice() -> int | None:
    with question_card("score"):
        score = st.selectbox(SCORE_QUESTION, tuple(SCORES), index=None, key=answer_key("score"),
                             placeholder="Válassz 1 és 10 pont között…")
        if score is not None:
            title, description = SCORES[score]
            st.html(f'<p class="geoterroir-score"><strong>{score}. {escape(title)}</strong> '
                    f'({escape(description)})</p>')
        with st.expander("A teljes értékelési skála"):
            st.markdown("\n\n".join(f"**{point}. {title}** ({description})"
                                     for point, (title, description) in SCORES.items()))
        return score


def attempt_save(lot: int | None = None) -> None:
    pending = st.session_state.get("wine_pending")
    if pending is None:
        try:
            evaluation = validate_evaluation(
                lot, {field: st.session_state.get(answer_key(field)) for field in ANSWER_KEYS},
            )
        except InvalidEvaluation as exc:
            st.error("Töltsd ki vagy ellenőrizd a következő kérdéseket: " + ", ".join(exc.fields) + ".")
            return
        pending = (uuid4(), evaluation)

    now = monotonic()
    if now - st.session_state.get("wine_last_attempt", -float("inf")) < 3:
        st.warning("Várj néhány másodpercet, majd próbáld újra.")
        return
    if not SUBMISSION_LIMIT.allow(st.context.ip_address):
        st.warning("Sok beküldés érkezik. Próbáld újra egy perc múlva.")
        return

    st.session_state.wine_last_attempt = now
    st.session_state.wine_pending = pending
    try:
        with st.spinner("Az értékelés mentése…"):
            submission_store().save(*pending)
    except DatabaseConfigurationError:
        st.session_state.wine_save_error = SETUP_REQUIRED
        st.rerun()
    except DatabaseError:
        st.session_state.wine_save_error = SAVE_FAILURE
        st.rerun()
    else:
        st.session_state.pop("wine_pending", None)
        st.session_state.pop("wine_save_error", None)
        st.session_state.wine_submitted = True
        st.rerun()


def render_pending() -> None:
    _, evaluation = st.session_state.wine_pending
    st.error(st.session_state.get("wine_save_error", SAVE_FAILURE))
    with st.expander(lot_label(evaluation.lot), expanded=True):
        st.markdown(f"**Jellemző aromacsoportok** · {', '.join(evaluation.aromas)}")
        st.markdown(f"**Borkészítés** · {evaluation.technique}")
        st.markdown(f"**Szőlőfajta** · {evaluation.grape} ({evaluation.fragrance or evaluation.variety_group})")
        st.markdown(f"**Borvidék** · {evaluation.region}")
        st.markdown(f"**Egyensúly** · {evaluation.balance}")
        st.markdown(f"**Pontszám** · {evaluation.score}/10")
    if st.button("Mentés újrapróbálása", type="primary", width="stretch", key="wine_retry"):
        attempt_save()


def render_evaluation() -> None:
    with st.container(key="geoterroir-evaluation"):
        if HEADER_IMAGE.is_file():
            st.image(str(HEADER_IMAGE), width="stretch")

        st.html("""
            <h1 class="geoterroir-heading">Borértékelés</h1>
            <p class="geoterroir-intro">Válaszd ki az értékelni kívánt bortételt, majd válaszolj a kérdésekre!
            Az értékelés anonim, és csak néhány percet vesz igénybe.</p>
        """)

        if st.session_state.get("wine_submitted"):
            st.success(SUCCESS)
            st.button("Új tétel értékelése", on_click=restart, type="primary", width="stretch")
            return
        if st.session_state.get("wine_pending"):
            render_pending()
            return

        with question_card("lot"):
            lot = st.selectbox(LOT_QUESTION, tuple(LOTS), index=None, format_func=lot_label, key="wine_lot",
                               placeholder="Válassz tételt…", on_change=clear_answers)
        if lot is None:
            return

        with question_card("aromas"):
            st.multiselect(AROMA_QUESTION, tuple(AROMAS), key=answer_key("aromas"),
                           placeholder="Egy vagy több aromacsoport…")
            with st.expander("Aromacsoportok részletesen"):
                st.markdown("\n\n".join(f"**{name}** ({notes})" for name, notes in AROMAS.items()))
        single_choice(TECHNIQUE_QUESTION, TECHNIQUES, "technique")

        field, question, varieties = variety_branch(lot)
        branch = single_choice(question, varieties, field, on_change=clear_grape)
        if branch is not None:
            grape_question, grapes = varieties[branch]
            single_choice(grape_question, grapes, "grape")

        if field == "fragrance":
            region_choice()
            single_choice(BALANCE_QUESTION, BALANCES, "balance")
        else:
            single_choice(BALANCE_QUESTION, BALANCES, "balance")
            region_choice()

        score_choice()
        if st.button("Értékelés beküldése", type="primary", width="stretch", key="wine_submit"):
            attempt_save(lot)
