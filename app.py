import streamlit as st

from components.admin import render_admin
from components.evaluation import render_evaluation
from components.style import apply_styles
from database.db import DatabaseError
from database.settings import load_settings, lots_from_settings


def main() -> None:
    st.set_page_config(page_title="GEOTerroir", page_icon="🍷", layout="wide")
    apply_styles()
    if st.query_params.get("admin") == "1":
        render_admin()
        return

    try:
        lots = lots_from_settings(load_settings())
    except DatabaseError:
        st.error("A wine_votes.db adatbázis most nem érhető el. Próbáld meg újra.")
        return
    render_evaluation(lots)
    with st.container(key="geoterroir-footer"):
        st.markdown("[Adminisztráció](?admin=1)")


if __name__ == "__main__":
    main()
