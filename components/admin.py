from dataclasses import dataclass
from datetime import datetime, timezone
from hmac import compare_digest
from time import monotonic

import streamlit as st

from components.charts import render_charts
from database.db import DatabaseError, ResultsStore, SORT_ORDERS
from database.settings import results_store
from utils.constants import BUDAPEST, LOTS, WineLot, lot_label
from utils.export import csv_bytes, excel_bytes, export_filename, legacy_votes_frame, records_frame
from utils.rate_limit import LOGIN_LIMIT


TITLE = "GEOTerroir – Adminisztráció"
ADMIN_PASSWORD = "admin26"
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
        st.markdown("[Vissza a kóstolóhoz](?)")
        st.title(TITLE)
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
        elif compare_digest(candidate.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Helytelen jelszó.")


def logout() -> None:
    st.session_state.pop("admin_authenticated", None)
    clear_prepared_export()


@st.fragment(run_every=3)
def render_active_count(store: ResultsStore, lot: int) -> None:
    if not st.session_state.get("admin_authenticated"):
        return
    try:
        _, active = store.counts(lot)
    except DatabaseError:
        active = "–"
    with st.container(border=True, key="dg-card-active"):
        st.metric("Aktív értékelések", active)


def select_lot(number: int) -> None:
    st.session_state.admin_lot = number
    for key in ("admin_table_scope", "admin_export_scope", "admin_archive_scope"):
        st.session_state.pop(key, None)
    reset_table_page()
    clear_prepared_export()


def render_lot_bar(store: ResultsStore, lot: int) -> None:
    summary, chooser = st.columns([1.15, 4.85], gap="small", vertical_alignment="center")
    with summary:
        render_active_count(store, lot)
    with chooser, st.container(horizontal=True, gap="small", key="dg-lot-buttons"):
        for number, entry in LOTS.items():
            st.button(entry.name, key=f"dg-lot-{number}", type="primary" if number == lot else "secondary",
                      width=112, on_click=select_lot, args=(number,))


def choose_scope(label: str, lot: int, lots: dict[int, WineLot], *, key: str, all_first=False, on_change=None):
    primary = (None, lot) if all_first else (lot, None)
    historical = tuple(number for number in lots if number not in LOTS)
    return st.selectbox(label, (*primary, *historical), format_func=lambda number: lot_label(number, lots),
                        key=key, filter_mode=None, on_change=on_change)


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


def render_exports(store: ResultsStore, lot: int, lots: dict[int, WineLot]) -> None:
    export_lot = choose_scope("Letöltendő adatok", lot, lots, key="admin_export_scope", all_first=True,
                              on_change=clear_prepared_export)
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
        st.success(f"Letölthető {prepared.count} értékelés · {lot_label(export_lot, lots)}")

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
    try:
        if store.has_legacy_records():
            with st.expander("A korábbi kérdőív jelölései"):
                st.download_button("Korábbi jelölések CSV letöltése", csv_bytes(legacy_votes_frame(store.legacy_records())),
                                   file_name="korabbi_wine_votes.csv", mime="text/csv", on_click="ignore")
    except DatabaseError:
        st.error("A korábbi kérdőív jelölései most nem tölthetők be.")


@st.fragment(run_every=3)
def render_live_charts(store: ResultsStore, lot: int) -> None:
    if not st.session_state.get("admin_authenticated"):
        return
    try:
        active, averages = store.chart_data(lot)
    except DatabaseError:
        st.error("Az eredmények most nem tölthetők be.")
        return
    render_charts(active, lot, averages)


@st.dialog("Szavazatok törlése", dismissible=False)
def confirm_archive(store: ResultsStore, lot: int | None, cutoff: datetime, label: str) -> None:
    if not st.session_state.get("admin_authenticated"):
        st.rerun()
    st.write(label)
    if lot is None:
        st.warning("A művelet minden tételre vonatkozik. A szavazatok az adatbázisban és a letölthető fájlokban továbbra is megmaradnak.")
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
            st.session_state.admin_notice = ARCHIVE_SUCCESS
            st.rerun()


def render_admin() -> None:
    if not st.session_state.get("admin_authenticated"):
        render_login()
        return

    with st.container(key="geoterroir-admin"):
        st.html('<a class="dg-admin-brand" href="?" aria-label="Vissza a kóstolóhoz">GEOTerroir</a>')
        heading, actions = st.columns([3, 2], gap="small", vertical_alignment="center")
        heading.title("Kóstolási eredmények")
        with actions, st.container(horizontal=True, horizontal_alignment="right", gap="small"):
            st.button("Adatok frissítése", on_click=clear_prepared_export)
            st.button("Kijelentkezés", on_click=logout)
        notice = st.session_state.pop("admin_notice", None)
        if notice:
            st.success(notice)
        try:
            store = results_store()
            historical = store.historical_lot_types(after_lot=max(LOTS))
            lots = LOTS | {number: WineLot(f"{number}. tétel", wine_type) for number, wine_type in historical.items()}
        except DatabaseError:
            st.error("Az eredmények nem tölthetők be. Frissítsd az adatokat, majd próbáld újra.")
            return
        lot = st.session_state.get("admin_lot", 1)
        if lot not in LOTS:
            lot = 1
        render_lot_bar(store, lot)
        graphs, table, exports, archive = st.tabs(
            ("Diagramok", "Értékelések", "Exportálás", "Archiválás"),
            key="admin_section", on_change="rerun",
        )
        if graphs.open:
            with graphs:
                render_live_charts(store, lot)
        if table.open:
            with table:
                table_lot = choose_scope("Megjelenített tételek", lot, lots, key="admin_table_scope",
                                         on_change=reset_table_page)
                try:
                    total, active = store.counts(table_lot)
                except DatabaseError:
                    st.error("A táblázat most nem tölthető be.")
                else:
                    render_table(store, table_lot, total, active)
        if exports.open:
            with exports:
                render_exports(store, lot, lots)
        if archive.open:
            with archive, st.container(border=True):
                st.subheader("Szavazatok törlése a diagramokból")
                st.caption("Az archivált értékelések továbbra is megjelennek a történeti táblázatban és az exportokban.")
                archive_lot = choose_scope("Archiválandó tételek", lot, lots, key="admin_archive_scope")
                if st.button("Szavazatok törlése", key="admin_archive"):
                    confirm_archive(store, archive_lot, datetime.now(timezone.utc), lot_label(archive_lot, lots))
