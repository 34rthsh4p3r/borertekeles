from html import escape
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

import streamlit as st

from database.db import DatabaseError
from database.settings import submission_store
from utils.constants import (
    AROMAS, AROMA_QUESTION, BALANCES, BALANCE_QUESTION, LOTS, LOT_QUESTION,
    REGIONS, REGION_QUESTION, SCORES, SCORE_QUESTION, TECHNIQUES,
    TECHNIQUE_QUESTION, lot_label, variety_branch,
)
from utils.rate_limit import SUBMISSION_LIMIT
from utils.validation import Evaluation, InvalidEvaluation, validate_evaluation


HEADER_IMAGE = Path(__file__).resolve().parent.parent / "GEOTerroir_HUN.jpg"
ANSWER_KEYS = ("aromas", "technique", "fragrance", "variety_group", "grape", "region", "balance", "score")
SUCCESS = "Köszönjük az értékelést! A válaszaidat sikeresen rögzítettük."
SAVE_FAILURE = "A mentést nem sikerült visszaigazolni. A kitöltött válaszaid megmaradtak. Próbáld újra!"


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


def single_choice(label: str, options, name: str, *, placeholder: str = "Válassz…", on_change=None):
    with question_card(name):
        return st.selectbox(label, tuple(options), index=None, key=answer_key(name),
                            placeholder=placeholder, filter_mode=None, on_change=on_change)


def region_choice() -> str | None:
    return single_choice(REGION_QUESTION, REGIONS, "region", placeholder="Válassz borvidéket…")


def score_choice() -> int | None:
    with question_card("score"):
        score = st.selectbox(SCORE_QUESTION, tuple(SCORES), index=None, key=answer_key("score"),
                             placeholder="Válassz 1 és 10 pont között…", filter_mode=None)
        if score is not None:
            title, description = SCORES[score]
            st.html(f'<p class="geoterroir-score"><strong>{score}. {escape(title)}</strong> '
                    f'({escape(description)})</p>')
        with st.expander("A teljes értékelési skála"):
            st.markdown("\n\n".join(f"**{point}. {title}** ({description})"
                                     for point, (title, description) in SCORES.items()))
        return score


def submit_evaluation(lot: int) -> None:
    try:
        evaluation = validate_evaluation(
            lot, {field: st.session_state.get(answer_key(field)) for field in ANSWER_KEYS},
        )
    except InvalidEvaluation as exc:
        st.error("Töltsd ki vagy ellenőrizd a következő kérdéseket: " + ", ".join(exc.fields) + ".")
        return
    attempt_save((uuid4(), evaluation))


def attempt_save(pending: tuple[UUID, Evaluation]) -> None:
    now = monotonic()
    if now - st.session_state.get("wine_last_attempt", -float("inf")) < 3:
        st.warning("Várj néhány másodpercet, majd próbáld újra.")
        return
    if not SUBMISSION_LIMIT.allow(st.context.ip_address):
        st.warning("Sok beküldés érkezik. Próbáld újra egy perc múlva.")
        return

    st.session_state.wine_last_attempt = now
    st.session_state.wine_pending = pending
    submission_id, evaluation = pending
    try:
        with st.spinner("Az értékelés mentése…"):
            submission_store().save(submission_id, evaluation)
    except DatabaseError:
        st.rerun()
    else:
        st.session_state.pop("wine_pending", None)
        st.session_state.wine_submitted = evaluation
        st.rerun()


def render_answers(evaluation: Evaluation) -> None:
    field, branch_question, varieties = variety_branch(evaluation.wine_type)
    branch = evaluation.fragrance if field == "fragrance" else evaluation.variety_group
    grape_question, _ = varieties[branch]
    region = (REGION_QUESTION, evaluation.region)
    balance = (BALANCE_QUESTION, evaluation.balance)
    region_and_balance = (region, balance) if field == "fragrance" else (balance, region)
    answers = [
        (LOT_QUESTION, lot_label(evaluation.lot, LOTS)),
        (AROMA_QUESTION, ", ".join(evaluation.aromas)),
        (TECHNIQUE_QUESTION, evaluation.technique),
        (branch_question, branch),
        (grape_question, evaluation.grape),
        *region_and_balance,
        (SCORE_QUESTION, f"{evaluation.score}/10 · {SCORES[evaluation.score][0]}"),
    ]
    st.markdown("\n\n".join(f"**{question}**  \n{answer}" for question, answer in answers))


def render_pending() -> None:
    pending = st.session_state.wine_pending
    _, evaluation = pending
    st.error(SAVE_FAILURE)
    with st.expander("A kitöltött válaszaid", expanded=True):
        render_answers(evaluation)
    if st.button("Mentés újrapróbálása", type="primary", width="stretch", key="wine_retry"):
        attempt_save(pending)


def render_evaluation() -> None:
    with st.container(key="geoterroir-evaluation"):
        if HEADER_IMAGE.is_file():
            st.image(str(HEADER_IMAGE), width="stretch")

        submitted = st.session_state.get("wine_submitted")
        if submitted:
            st.success(SUCCESS)
            if isinstance(submitted, Evaluation):
                with question_card("summary"):
                    st.subheader("A válaszaid")
                    render_answers(submitted)
            st.button("Új tétel értékelése", on_click=restart, type="primary", width="stretch")
            return
        if st.session_state.get("wine_pending"):
            render_pending()
            return

        with question_card("lot"):
            if st.session_state.get("wine_lot") not in (None, *LOTS):
                st.session_state.pop("wine_lot", None)
            lot = st.selectbox(LOT_QUESTION, tuple(LOTS), index=None, format_func=lambda value: lot_label(value, LOTS),
                               key="wine_lot", placeholder="Válassz tételt…", filter_mode=None,
                               on_change=clear_answers)
        if lot is None:
            return

        with question_card("aromas"):
            st.multiselect(AROMA_QUESTION, tuple(AROMAS), key=answer_key("aromas"),
                           placeholder="Egy vagy több aromacsoport…", filter_mode=None, select_all=False)
            with st.expander("Aromacsoportok részletesen"):
                st.markdown("\n\n".join(f"**{name}** ({notes})" for name, notes in AROMAS.items()))
        single_choice(TECHNIQUE_QUESTION, TECHNIQUES, "technique")

        field, question, varieties = variety_branch(LOTS[lot].wine_type)
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
            submit_evaluation(lot)
