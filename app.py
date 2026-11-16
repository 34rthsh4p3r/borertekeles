import streamlit as st

from components.admin import render_admin
from components.evaluation import render_evaluation
from components.style import apply_styles


st.set_page_config(page_title="GeoTerroir", page_icon="🍷", layout="wide")
page = st.navigation(
    [
        st.Page(render_evaluation, title="Borértékelés", default=True),
        st.Page(render_admin, title="Eredmények", url_path="eredmenyek"),
    ],
    position="top",
)
apply_styles()
page.run()
