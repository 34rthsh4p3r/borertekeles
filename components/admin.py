from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest
from time import monotonic

import pandas as pd
import streamlit as st

from components.charts import render_charts
from database.db import DatabaseError, ResultsStore, SORT_ORDERS
from database.settings import results_store, secret
from utils.aggregates import answer_counts, aroma_counts, decimal_label, score_statistics
from utils.constants import BUDAPEST, LOTS, lot_label
from utils.export import csv_bytes, excel_bytes, export_filename, records_frame
from utils.rate_limit import LOGIN_LIMIT


TITLE = "GEOTerroir – Adminisztráció"
PAGE_SIZE = 100
ARCHIVE_SUCCESS = (
    "A szavazatokat eltávolítottuk az aktuális diagramokból. "
    "Az archivált válaszok továbbra is elérhetők az exportálható adatbázisban."
)


@dataclass(frozen=True)
class PreparedExport:
    lot: int | None
    created_at: datetime
    count: int
    csv: bytes
    excel: bytes


def render_login() -> None:
    with st.container(key="geoterroir-login"):
        st.title(TITLE)
        password = secret("ADMIN_PASSWORD")
        if not isinstance(password, str) or not password.strip():
            st.info("Az adminisztrátori belépéshez még be kell állítani a jelszót.")
            return
        with st.form("admin_login", clear_on_submit=True):
            candidate = st.text_input("Adminisztrátori jelszó", type="password", max_chars=256)
            submitted = st.form_submit_button("Belépés", type="primary", width="stretch")
        if not submitted:
            return

        now = monotonic()
        if now - st.session_state.get("admin_login_attempt", -float("inf")) < 2:
            st.warning("Várj néhány másodpercet a következő belépési kísérlet előtt.")
            return
        st.session_state.admin_login_attempt = now
        if not LOGIN_LIMIT.allow(st.context.ip_address):
            st.warning("Túl sok belépési kísérlet. Próbáld meg egy perc múlva.")
        elif compare_digest(candidate.encode("utf-8"), password.encode("utf-8")):
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Helytelen jelszó.")


def logout() -> None:
    st.session_state.pop("admin_authenticated", None)
    clear_prepared_export()


def render_statistics(counts: dict[int, int], active: list[dict], lot: int | None) -> None:
    _, average, _ = score_statistics(active)
    most_common = aroma_counts(active).most_common(1)[0][0] if active else "–"
    first, second = st.columns(2)
    first.metric("Összes rögzített értékelés", sum(counts.values()), border=True)
    second.metric("Diagramokon aktív értékelések", len(active), border=True)
    third, fourth = st.columns(2)
    third.metric("Átlagpontszám · aktív", decimal_label(average), border=True)
    fourth.metric("Leggyakoribb aromacsoport · aktív", most_common, border=True)

    active_counts = answer_counts(active, "lot")
    with st.expander("Értékelések száma tételenként", expanded=True):
        rows = [(lot_label(number), counts.get(number, 0), active_counts[number])
                for number in ((lot,) if lot is not None else LOTS)]
        st.dataframe(pd.DataFrame(rows, columns=["Tétel", "Összes rögzített", "Diagramokon aktív"]),
                     hide_index=True, width="stretch")


def reset_table_page() -> None:
    st.session_state.pop("admin_table_page", None)


def render_table(store: ResultsStore, lot: int | None, history_count: int, active_count: int) -> None:
    active_only = st.toggle("Csak a diagramokon aktív értékelések", value=True, key="admin_active_only",
                           on_change=reset_table_page)
    count = active_count if active_only else history_count
    if not count:
        st.info("Ehhez a tételhez még nem érkezett aktív értékelés." if active_only
                else "Ehhez a tételhez még nem érkezett értékelés.")
        return

    sort = st.selectbox("Rendezés", tuple(SORT_ORDERS), key="admin_sort", on_change=reset_table_page)
    max_page = (count - 1) // PAGE_SIZE + 1
    if st.session_state.get("admin_table_page", 1) > max_page:
        st.session_state.admin_table_page = max_page
    page = st.number_input("Oldal", min_value=1, max_value=max_page, step=1, key="admin_table_page",
                           disabled=max_page == 1)
    offset = (page - 1) * PAGE_SIZE
    try:
        records = store.records(lot, active_only=active_only, sort=sort, limit=PAGE_SIZE, offset=offset)
    except DatabaseError:
        st.error("A táblázat nem tölthető be. Próbáld meg újra az adatok frissítését!")
        return
    st.caption(f"{offset + 1}–{min(offset + PAGE_SIZE, count)} / {count} értékelés")
    st.dataframe(records_frame(records), width="stretch", height=380, hide_index=True,
                 column_config={"Dátum": st.column_config.DateColumn(format="YYYY-MM-DD"),
                                "Diagram aktív": st.column_config.CheckboxColumn()})


def clear_prepared_export() -> None:
    st.session_state.pop("admin_prepared_export", None)


def render_exports(store: ResultsStore, lot: int | None) -> None:
    export_lot = None
    if lot is not None:
        selected_lot = st.radio(
            "Letöltendő adatok", (False, True), key="admin_export_scope", on_change=clear_prepared_export,
            format_func=lambda selected: "A kiválasztott tétel történeti értékelései" if selected
            else "Összes történeti értékelés",
        )
        if selected_lot:
            export_lot = lot
    st.caption("Az előkészített fájlok az archivált válaszokat is tartalmazzák.")
    if st.button("Exportfájlok előkészítése", type="primary"):
        clear_prepared_export()
        try:
            with st.spinner("Az exportfájlok előkészítése…"):
                generated_at = datetime.now(BUDAPEST)
                frame = records_frame(store.records(export_lot))
                st.session_state.admin_prepared_export = PreparedExport(
                    export_lot, generated_at, len(frame), csv_bytes(frame), excel_bytes(frame),
                )
        except DatabaseError:
            st.error("Az export nem készíthető el. Frissítsd az adatokat, majd próbáld újra!")

    prepared = st.session_state.get("admin_prepared_export")
    if prepared is not None and prepared.lot != export_lot:
        clear_prepared_export()
        prepared = None
    if prepared is not None:
        st.success(f"Letölthető {prepared.count} értékelés · {lot_label(export_lot)}")

    csv_column, excel_column = st.columns(2)
    csv_column.download_button(
        "CSV letöltése", prepared.csv if prepared else b"", mime="text/csv",
        file_name=export_filename(export_lot, "csv", prepared.created_at) if prepared else None,
        disabled=prepared is None, on_click="ignore", width="stretch", key="admin_csv",
    )
    excel_column.download_button(
        "Excel letöltése", prepared.excel if prepared else b"",
        file_name=export_filename(export_lot, "xlsx", prepared.created_at) if prepared else None,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=prepared is None, on_click="ignore", width="stretch", key="admin_excel",
    )


@st.dialog("Szavazatok törlése", dismissible=False)
def confirm_archive(store: ResultsStore, lot: int | None, cutoff: datetime) -> None:
    if not st.session_state.get("admin_authenticated"):
        st.rerun()
    st.markdown(f"**{lot_label(lot)}**")
    if lot is None:
        st.warning("A művelet mind az öt tételre vonatkozik. A szavazatok az adatbázisban és a letölthető fájlokban továbbra is megmaradnak.")
        confirmed = st.checkbox("Megerősítem, hogy az összes tétel szavazatait eltávolítom a diagramokból.")
    else:
        st.write("Biztosan törölni szeretnéd a kiválasztott tétel szavazatait a diagramokból? "
                 "A szavazatok az adatbázisban és a letölthető fájlokban továbbra is megmaradnak.")
        confirmed = True

    left, right = st.columns([1, 2])
    if left.button("Mégse", width="stretch"):
        st.rerun()
    if right.button("Igen, szavazatok törlése", type="primary", width="stretch", disabled=not confirmed):
        try:
            with st.spinner("A diagramok frissítése…"):
                store.archive(lot, cutoff)
        except DatabaseError:
            st.error("A műveletet nem sikerült visszaigazolni. Próbáld újra!")
        else:
            clear_prepared_export()
            st.session_state.admin_archive_notice = ARCHIVE_SUCCESS
            st.rerun()


def render_admin() -> None:
    if not st.session_state.get("admin_authenticated"):
        render_login()
        return

    with st.container(key="geoterroir-admin"):
        st.title(TITLE)
        with st.container(horizontal=True):
            st.button("Adatok frissítése", on_click=clear_prepared_export)
            st.button("Kijelentkezés", on_click=logout)
        notice = st.session_state.pop("admin_archive_notice", None)
        if notice:
            st.success(notice)
        lot = st.selectbox("Válaszd ki a megtekinteni kívánt tételt!", (None, *LOTS),
                           format_func=lot_label, key="admin_lot", on_change=reset_table_page)
        try:
            store = results_store()
            with st.spinner("Eredmények betöltése…"):
                counts, active = store.dashboard(lot)
        except DatabaseError:
            st.error("Az eredmények nem tölthetők be. Ellenőrizd az adatbázis beállításait, majd frissítsd az adatokat!")
            return

        render_statistics(counts, active, lot)
        graphs, table, exports, archive = st.tabs(
            ("Diagramok", "Értékelések", "Exportálás", "Archiválás"), key="admin_section", on_change="rerun",
        )
        if graphs.open:
            with graphs:
                render_charts(active, lot)
        if table.open:
            with table:
                render_table(store, lot, sum(counts.values()), len(active))
        if exports.open:
            with exports:
                render_exports(store, lot)
        if archive.open:
            with archive, st.container(border=True):
                st.subheader("Szavazatok törlése a diagramokból")
                st.caption("Az archivált értékelések továbbra is megjelennek a történeti táblázatban és az exportokban.")
                if st.button("Szavazatok törlése", disabled=not active, key="admin_archive"):
                    try:
                        cutoff = store.current_time()
                    except DatabaseError:
                        st.error("Az archiválás nem indítható el. Frissítsd az adatokat, majd próbáld újra!")
                    else:
                        confirm_archive(store, lot, cutoff)
