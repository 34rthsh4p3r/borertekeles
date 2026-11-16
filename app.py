"""Bordó-fehér GEOTerroir borkóstoló, automatikus SQLite-mentéssel."""

import os
import sqlite3
from collections import defaultdict
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hmac import compare_digest
from html import escape
from inspect import signature
from io import BytesIO
from pathlib import Path
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


APP_TITLE = "Borok értékelése"
DB_PATH = Path(__file__).with_name("wine_votes.db")
LOGO_PATH = Path(__file__).with_name("GEOTerroir_HUN.jpg")
DEFAULT_WINE_COUNT = 5
MAX_WINE_COUNT = 20
PRIMARY_SECTION = "elsodleges"
PRIMARY_QUESTION = "elsodleges_aromak"
PRIMARY_SECTIONS = (PRIMARY_SECTION, "illat", "iz")
BUDAPEST = ZoneInfo("Europe/Budapest")

PRIMARY_AROMAS = {
    "Florális": ["akác", "kamilla", "bodza", "virág", "rózsa", "ibolya"],
    "Éretlen gyümölcs": ["zöldalma", "egres", "körte", "szőlő"],
    "Citrusféle": ["grapefruit", "citrom", "lime", "narancs"],
    "Csonthéjas": ["őszibarack", "sárgabarack", "nektarin"],
    "Trópusi": ["banán", "licsi", "mangó", "dinnye", "maracuja", "ananász"],
    "Piros bogyós": ["ribizli", "vörösáfonya", "málna", "eper", "meggy", "cseresznye"],
    "Fekete bogyós": ["feketeribizli", "szeder", "kékáfonya", "kései meggy", "szilva"],
    "Fűszeres": ["fűszer", "fekete bors", "fehér bors", "édesgyökér (medvecukor)"],
    "Füves": ["zöldpaprika", "fű", "paradicsomlevél", "spárga"],
    "Gyógynövényes": ["eukaliptusz", "menta", "édeskömény", "kapor"],
}

SECONDARY_AROMAS = {
    "Élesztő": ["keksz", "kenyér", "pirítós", "kenyértészta", "sajt", "joghurt"],
    "Malolaktikus erjedés": ["vaj", "tejszín", "sajt", "joghurt"],
    "Tölgyfahordós jegyek": [
        "vanília", "szegfűszeg", "szerecsendió", "kókusz", "karamella",
        "pirítós", "égett fa", "füst", "csokoládé", "kávé", "gyanta", "cédrus"
    ],
}

TERTIARY_AROMAS = {
    "Oxidáció": ["mandula", "mogyoró", "dió", "csokoládé", "kávé", "karamell"],
    "Vörösbor": ["szárított gyümölcs", "bőr", "föld", "gomba", "erdei talaj", "hús", "dohány", "nedves levél", "karamell"],
    "Fehérbor": ["szárított gyümölcs", "narancslekvár", "petrol (benzin)", "fahéj", "gyömbér", "szerecsendió", "mogyoró", "méz", "karamell"],
}

SCALE_QUESTIONS = {
    "illat": [
        ("intenzitas", "Illat intenzitása", ["Visszafogott", "Közepes", "Határozott"]),
    ],
    "iz": [
        ("edesseg", "Édesség", ["Száraz", "Félszáraz", "Félédes", "Édes"]),
        ("savassag", "Savasság", ["Alacsony", "Közepes", "Magas"]),
        ("tannin", "Tannin", ["Nincs", "Alacsony", "Közepes", "Magas"]),
        ("alkohol", "Alkohol", ["Alacsony", "Közepes", "Magas"]),
        ("testesseg", "Testesség", ["Könnyű", "Közepes", "Telt"]),
        ("intenzitas", "Intenzitás", ["Könnyű", "Közepes", "Határozott"]),
        ("lecsenges", "Lecsengés", ["Rövid", "Közepes", "Hosszú"]),
    ],
}

WINE_TYPES = {"Fehér": "#e0d477", "Rozé": "#e97a8d", "Vörös": "#a52a47"}
AROMA_SECTIONS = {
    PRIMARY_SECTION: (PRIMARY_QUESTION, "Elsődleges aromák", PRIMARY_AROMAS),
    "masodlagos": ("aromak", "Másodlagos aromák", SECONDARY_AROMAS),
    "harmadlagos": ("aromak", "Harmadlagos aromák", TERTIARY_AROMAS),
}
SINGLE_OPTIONS = {(section, key): tuple(options)
                  for section, questions in SCALE_QUESTIONS.items() for key, _, options in questions}
MULTI_OPTIONS = {
    (section, question): tuple(f"{group} → {option}" for group, entries in groups.items() for option in entries)
    for section, (question, _, groups) in AROMA_SECTIONS.items()
}
MULTI_OPTIONS[PRIMARY_SECTION, PRIMARY_QUESTION] += tuple(PRIMARY_AROMAS)
VOTE_COLUMNS = ("participant", "wine", "section", "question", "option", "created_at", "archived_at")


@contextmanager
def connect(path):
    with closing(sqlite3.connect(path, timeout=8)) as database, database:
        database.row_factory = sqlite3.Row
        yield database


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def init_db(path):
    with connect(path) as database:
        database.execute("PRAGMA journal_mode = WAL").fetchone()
        database.execute("BEGIN IMMEDIATE")
        database.execute("""CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, participant TEXT NOT NULL,
            wine INTEGER NOT NULL DEFAULT 1, section TEXT NOT NULL, question TEXT NOT NULL,
            option TEXT NOT NULL, created_at TEXT NOT NULL, archived_at TEXT
        )""")
        database.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        columns = {row["name"] for row in database.execute("PRAGMA table_info(votes)")}
        if "wine" not in columns:
            database.execute("ALTER TABLE votes ADD COLUMN wine INTEGER NOT NULL DEFAULT 1")
        if "archived_at" not in columns:
            database.execute("ALTER TABLE votes ADD COLUMN archived_at TEXT")
        # A régi egyedi indexek az archivált jelölés későbbi újraválasztását is tiltották.
        database.execute("DROP INDEX IF EXISTS uq_vote")
        database.execute("DROP INDEX IF EXISTS uq_vote_wine")
        database.execute("CREATE INDEX IF NOT EXISTS votes_lot_state ON votes(wine, archived_at)")
        database.execute("CREATE INDEX IF NOT EXISTS votes_participant ON votes(participant, wine, archived_at)")


@st.cache_resource(show_spinner=False)
def prepare_db(path):
    init_db(path)
    return path


def load_settings(path):
    with connect(path) as database:
        return dict(database.execute("SELECT key, value FROM settings").fetchall())


def save_settings(path, settings):
    with connect(path) as database:
        database.executemany(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [(key, str(value)) for key, value in settings.items()],
        )


def wine_count(settings):
    try:
        return max(1, min(int(settings.get("wine_count", DEFAULT_WINE_COUNT)), MAX_WINE_COUNT))
    except (TypeError, ValueError):
        return DEFAULT_WINE_COUNT


def wine_name(settings, wine):
    return settings.get(f"wine_{wine}_name") or f"{wine}. tétel"


def wine_type(settings, wine):
    name = settings.get(f"wine_{wine}_type")
    return name if name in WINE_TYPES else "Fehér"


def answer_scope(participant, wine, section, question):
    where = "participant = ? AND wine = ? AND archived_at IS NULL AND question = ?"
    params = (participant, wine, question)
    if (section, question) == (PRIMARY_SECTION, PRIMARY_QUESTION):
        return where + " AND section IN (?, ?, ?)", (*params, *PRIMARY_SECTIONS)
    return where + " AND section = ?", (*params, section)


def update_answer(path, participant, wine, section, question, option):
    key = (section, question)
    multi = key in MULTI_OPTIONS
    choices = MULTI_OPTIONS[key] if multi else SINGLE_OPTIONS.get(key, ())
    if option not in choices or not 1 <= wine <= MAX_WINE_COUNT:
        raise ValueError("Érvénytelen választás.")

    where, params = answer_scope(participant, wine, section, question)
    with connect(path) as database:
        database.execute("BEGIN IMMEDIATE")
        previous = {row["option"] for row in database.execute(f"SELECT option FROM votes WHERE {where}", params)}
        if multi:
            # A régi jelölések együtt frissülnek a közös elsődleges szekcióban.
            selected = previous ^ {option}
        else:
            selected = {option}
            if selected == previous:
                return
        database.execute(f"DELETE FROM votes WHERE {where}", params)
        now = utc_now()
        database.executemany(
            """INSERT INTO votes (participant, wine, section, question, option, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(participant, wine, section, question, value, now) for value in sorted(selected)],
        )


def active_answers(path, participant, wine):
    with connect(path) as database:
        rows = database.execute(
            "SELECT section, question, option FROM votes WHERE participant = ? AND wine = ? AND archived_at IS NULL",
            (participant, wine),
        ).fetchall()
    answers = defaultdict(set)
    for section, question, option in rows:
        if question == PRIMARY_QUESTION and section in PRIMARY_SECTIONS:
            section = PRIMARY_SECTION
        answers[section, question].add(option)
    return answers


def fetch_votes(path, wine=None, *, active_only=False):
    clauses = []
    params = []
    if wine is not None:
        clauses.append("wine = ?")
        params.append(wine)
    if active_only:
        clauses.append("archived_at IS NULL")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    columns = ", ".join(VOTE_COLUMNS)
    with connect(path) as database:
        frame = pd.read_sql_query(f"SELECT {columns} FROM votes{where} ORDER BY id", database, params=params)
    primary = frame["section"].isin(PRIMARY_SECTIONS) & frame["question"].eq(PRIMARY_QUESTION)
    frame.loc[primary, "section"] = PRIMARY_SECTION
    repeated = frame.duplicated(subset=["participant", "wine", "section", "question", "option", "archived_at"])
    return frame.loc[~(primary & repeated)].reset_index(drop=True)


def archive_votes(path, wine=None):
    with connect(path) as database:
        if wine is None:
            return database.execute("UPDATE votes SET archived_at = ? WHERE archived_at IS NULL", (utc_now(),)).rowcount
        return database.execute(
            "UPDATE votes SET archived_at = ? WHERE archived_at IS NULL AND wine = ?", (utc_now(), wine),
        ).rowcount


def result_table(frame, section, question, *, options=None, detail=False):
    answers = frame.loc[frame["section"].eq(section) & frame["question"].eq(question)]
    voters = answers["participant"].nunique()
    answers = answers.loc[answers["option"].str.contains(" → ", regex=False).eq(detail)]
    counts = answers.groupby("option")["participant"].nunique()
    if options is not None:
        counts = counts.reindex(options, fill_value=0)
    else:
        counts = counts.sort_values(ascending=False, kind="stable")
    percentages = (counts / max(voters, 1) * 100).round(1)
    return zip(counts.index, counts, percentages), voters


def export_frame(path, settings, wine=None):
    frame = fetch_votes(path, wine)
    times = pd.to_datetime(frame["created_at"], utc=True, format="mixed", errors="coerce").dt.tz_convert(BUDAPEST)
    frame.insert(0, "Timestamp (HH-MM-SS)", times.dt.strftime("%H-%M-%S"))
    frame.insert(1, "Dátum", times.dt.strftime("%Y-%m-%d"))
    frame.insert(4, "wine_name", frame["wine"].map(lambda lot: wine_name(settings, lot)))
    frame.insert(5, "wine_type", frame["wine"].map(lambda lot: wine_type(settings, lot)))
    frame["Diagram aktív"] = frame["archived_at"].isna()
    return frame


def export_excel(frame):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Szavazatok", index=False)
        sheet = writer.sheets["Szavazatok"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
        for index, cell in enumerate(sheet[1], start=1):
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="7B2341")
            sheet.column_dimensions[get_column_letter(index)].width = max(20, len(str(cell.value)) + 3)
    return output.getvalue()


def stretch(widget):
    width = signature(widget).parameters.get("width")
    if width is not None and width.default in ("content", "stretch"):
        return {"width": "stretch"}
    return {"use_container_width": True}


def choice_buttons(options, selected, key, select, *, columns=3, label=str):
    for start in range(0, len(options), columns):
        row = st.columns(columns, gap="small")
        for offset, option in enumerate(options[start:start + columns]):
            picked = option in selected
            st_key = f"{'picked' if picked else 'choice'}-{key}-{start + offset}"
            row[offset].button(
                label(option), key=st_key, type="primary" if picked else "secondary",
                on_click=select, args=(option,), **stretch(st.button),
            )


def participant_id():
    if "participant_id" not in st.session_state:
        st.session_state.participant_id = uuid4().hex
    return st.session_state.participant_id


def vote_buttons(path, options, selected, key, wine, section, question, *, columns=3, label=str):
    def save(option):
        try:
            update_answer(path, participant_id(), wine, section, question, option)
        except sqlite3.Error:
            st.session_state.vote_error = "A választás mentése nem sikerült. Próbáld meg újra."

    choice_buttons(options, selected, key, save, columns=columns, label=label)


def render_scales(path, wine, answers, section):
    for key, label, options in SCALE_QUESTIONS[section]:
        st.markdown(f"**{label}**")
        vote_buttons(path, options, answers.get((section, key), set()), f"w{wine}-{section}-{key}",
                     wine, section, key, columns=min(4, len(options)))


def render_aromas(path, wine, answers, section):
    question, title, groups = AROMA_SECTIONS[section]
    st.header(title)
    selected = answers.get((section, question), set())
    if section == PRIMARY_SECTION:
        st.markdown("**Aromacsoportok**")
        vote_buttons(path, list(groups), selected, f"w{wine}-{section}-groups", wine, section, question)
    for index, (group, entries) in enumerate(groups.items()):
        options = [f"{group} → {entry}" for entry in entries]
        with st.expander(group):
            vote_buttons(path, options, selected, f"w{wine}-{section}-detail-{index}", wine, section, question,
                         label=lambda value: value.split(" → ", 1)[1])


def set_state(value, key):
    st.session_state[key] = value


def lot_buttons(settings, key):
    count = wine_count(settings)
    wine = st.session_state.get(key, 1)
    if not 1 <= wine <= count:
        wine = 1
    choice_buttons(list(range(1, count + 1)), {wine}, key,
                   lambda option: set_state(option, key), label=lambda option: wine_name(settings, option))
    return wine


def render_tasting(path, settings):
    logo, title = st.columns([1.25, 3.75], vertical_alignment="center")
    with logo:
        if LOGO_PATH.is_file():
            st.image(str(LOGO_PATH), **stretch(st.image))
    with title:
        st.title(settings.get("tasting_name") or APP_TITLE)

    st.markdown("**Melyik tételt értékeled?**")
    wine = lot_buttons(settings, "active-wine")
    st.caption(f"{wine_type(settings, wine)}bor · A választásaid automatikusan mentésre kerülnek.")
    error = st.session_state.pop("vote_error", None)
    if error:
        st.error(error)
    answers = active_answers(path, participant_id(), wine)

    st.divider()
    st.header("Illat intenzitása")
    render_scales(path, wine, answers, "illat")
    st.divider()
    st.header("Ízösszetétel")
    render_scales(path, wine, answers, "iz")
    for section in AROMA_SECTIONS:
        st.divider()
        render_aromas(path, wine, answers, section)

    st.divider()
    st.caption("Geoterroir Kutatócsoport 2026")
    st.markdown("[Adminisztráció](?admin=1)")


def admin_password():
    try:
        password = st.secrets.get("ADMIN_PASSWORD")
    except FileNotFoundError:
        password = None
    return password if isinstance(password, str) and password else os.getenv("ADMIN_PASSWORD")


def login():
    password = admin_password()
    if not password:
        st.info("Az adminisztrációhoz állítsd be az ADMIN_PASSWORD értékét.")
        return
    with st.form("admin-login", clear_on_submit=True):
        candidate = st.text_input("Admin jelszó", type="password", max_chars=256)
        submitted = st.form_submit_button("Belépés", type="primary", **stretch(st.form_submit_button))
    if submitted:
        now = monotonic()
        if now - st.session_state.get("admin_last_attempt", -float("inf")) < 2:
            st.warning("Várj néhány másodpercet a következő próbálkozás előtt.")
            return
        st.session_state.admin_last_attempt = now
        if compare_digest(candidate.encode("utf-8"), password.encode("utf-8")):
            st.session_state.admin_authenticated = True
            st.rerun()
        st.error("Helytelen jelszó.")


def logout():
    st.session_state.pop("admin_authenticated", None)
    st.session_state.pop("prepared_export", None)


def render_settings(path, settings):
    with st.form("tasting-settings"):
        name = st.text_input("Kóstoló címe", settings.get("tasting_name") or APP_TITLE, max_chars=120)
        count = st.number_input("Hány tétel legyen?", min_value=1, max_value=MAX_WINE_COUNT,
                                value=wine_count(settings), step=1)
        if st.form_submit_button("Kóstoló beállításainak mentése"):
            save_settings(path, {"tasting_name": name.strip() or APP_TITLE, "wine_count": count})
            st.session_state.admin_notice = "A kóstoló beállításait mentettük."
            st.rerun()

    st.subheader("Tételek")
    changes = {}
    types = list(WINE_TYPES)
    with st.form("wine-settings"):
        for wine in range(1, wine_count(settings) + 1):
            with st.expander(f"{wine}. tétel – {wine_name(settings, wine)}", expanded=wine == 1):
                name = st.text_input("Tétel neve", wine_name(settings, wine), max_chars=100, key=f"wine-name-{wine}")
                category = st.radio("Bor típusa", types, index=types.index(wine_type(settings, wine)),
                                    horizontal=True, key=f"wine-type-{wine}")
                changes[f"wine_{wine}_name"] = name.strip() or f"{wine}. tétel"
                changes[f"wine_{wine}_type"] = category
        if st.form_submit_button("Tételek adatainak mentése"):
            save_settings(path, changes)
            st.session_state.pop("prepared_export", None)
            st.session_state.admin_notice = "A tételek adatait mentettük."
            st.rerun()


def render_bars(frame, section, question, title, color, *, options=None, detail=False):
    rows, voters = result_table(frame, section, question, options=options, detail=detail)
    st.markdown(f"**{title}**")
    bars = []
    for label, count, percent in rows:
        percentage = f"{percent:g}".replace(".", ",")
        label = escape(label.replace(" → ", " – "))
        bars.append(
            f'<div class="summary-row"><span>{label}</span>'
            f'<div class="summary-track" aria-hidden="true"><div style="width:{percent:.1f}%;background:{color}"></div></div>'
            f'<strong>{percentage}% · {count} fő</strong></div>'
        )
    if voters and bars:
        st.html('<div class="summary-chart">' + "".join(bars) + '</div>')
    else:
        st.caption("Még nincs jelölés.")


@st.fragment(run_every=3)
def render_live_results(path, settings, wine):
    if not st.session_state.get("admin_authenticated"):
        return
    try:
        frame = fetch_votes(path, wine, active_only=True)
    except sqlite3.Error:
        st.error("Az eredményeket most nem sikerült beolvasni.")
        return
    st.subheader(wine_name(settings, wine))
    st.caption(f"{wine_type(settings, wine)}bor · {frame['participant'].nunique()} résztvevő")
    if frame.empty:
        st.info("Ehhez a tételhez még nem érkezett aktív értékelés.")
        return
    color = WINE_TYPES[wine_type(settings, wine)]
    for section, questions in SCALE_QUESTIONS.items():
        with st.container(border=True):
            if section == "iz":
                st.subheader("Ízösszetétel")
            for question, label, options in questions:
                render_bars(frame, section, question, label, color, options=options)

    for section, (question, title, _) in AROMA_SECTIONS.items():
        with st.container(border=True):
            if section == PRIMARY_SECTION:
                render_bars(frame, section, question, title, color)
                with st.expander("Részletes elsődleges aromák"):
                    render_bars(frame, section, question, "Illat- és ízjegyek", color, detail=True)
            else:
                render_bars(frame, section, question, title, color, detail=True)


@st.dialog("Szavazatok archiválása")
def confirm_archive(path, wine, label):
    if not st.session_state.get("admin_authenticated"):
        st.rerun()
    st.write(f"{label} aktív jelölései lekerülnek a diagramokról. A teljes történet letölthető marad.")
    approved = wine is not None or st.checkbox("Megerősítem az összes tétel archiválását.")
    cancel, approve = st.columns(2)
    if cancel.button("Mégse"):
        st.rerun()
    if approve.button("Szavazatok archiválása", type="primary", disabled=not approved):
        try:
            count = archive_votes(path, wine)
        except sqlite3.Error:
            st.error("Az archiválás most nem sikerült. Próbáld meg újra.")
            return
        st.session_state.pop("prepared_export", None)
        st.session_state.admin_notice = f"{count} jelölés archiválva. A történeti exportban továbbra is szerepelnek."
        st.rerun()


def render_exports(path, settings):
    st.subheader("Történeti export")
    lots = list(range(1, wine_count(settings) + 1))
    label = lambda wine: "Összes tétel" if wine == 0 else wine_name(settings, wine)
    wine = st.selectbox("Exportált tételek", [0, *lots], format_func=label, key="export-scope") or None
    if st.button("Exportfájlok előkészítése"):
        st.session_state.pop("prepared_export", None)
        try:
            frame = export_frame(path, settings, wine)
        except sqlite3.Error:
            st.error("Az exportot most nem sikerült előkészíteni.")
        else:
            stamp = datetime.now(BUDAPEST).strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"wine_votes_{'osszes' if wine is None else f'tetel-{wine}'}_{stamp}"
            csv = frame.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.session_state.prepared_export = (wine, filename, csv, export_excel(frame))
    prepared = st.session_state.get("prepared_export")
    if prepared and prepared[0] == wine:
        _, filename, csv, excel = prepared
        left, right = st.columns(2)
        left.download_button("CSV letöltése", csv, file_name=f"{filename}.csv", mime="text/csv")
        right.download_button("Excel letöltése", excel, file_name=f"{filename}.xlsx",
                              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.divider()
    st.subheader("Archiválás")
    wine = st.selectbox("Archiválandó tétel", [*lots, 0], format_func=label, key="archive-scope")
    if st.button("Szavazatok törlése a diagramokból"):
        confirm_archive(path, wine or None, label(wine))


def render_admin(path, settings):
    st.title("GEOTerroir – Adminisztráció")
    st.markdown("[Vissza a kóstolóhoz](?)")
    if not st.session_state.get("admin_authenticated"):
        login()
        return
    st.button("Kijelentkezés", on_click=logout)
    notice = st.session_state.pop("admin_notice", None)
    if notice:
        st.success(notice)
    view = st.radio("Adminisztráció", ("Eredmények", "Beállítások", "Export és archiválás"),
                    horizontal=True, label_visibility="collapsed")
    if view == "Eredmények":
        st.markdown("**Összesítés megtekintése – tétel**")
        render_live_results(path, settings, lot_buttons(settings, "admin-summary-wine"))
    elif view == "Beállítások":
        render_settings(path, settings)
    else:
        render_exports(path, settings)


def apply_styles():
    st.html("""
    <style>
    h1, h2, h3 { color: #7b2341; }
    [class*="st-key-choice-"] button, [class*="st-key-picked-"] button {
        min-height: 44px;
        height: auto;
        padding: .55rem .65rem;
        white-space: normal;
        overflow-wrap: anywhere;
        border-radius: .85rem;
        box-shadow: 0 3px 10px #4a182c12;
    }
    [class*="st-key-choice-"] button { background: #fff; color: #7b2341; border-color: #e5cdd5; }
    [class*="st-key-choice-"] button:hover { background: #f9edf1; color: #601a32; border-color: #7b2341; }
    [class*="st-key-picked-"] button, [class*="st-key-picked-"] button:hover {
        background: #f4f1ba; border-color: #b3a74c; color: #35252c;
    }
    [class*="st-key-choice-"] button:focus-visible, [class*="st-key-picked-"] button:focus-visible {
        outline: 3px solid #ba6d86; outline-offset: 2px;
    }
    .summary-chart { margin: .4rem 0 1rem; }
    .summary-row {
        display: grid;
        grid-template-columns: minmax(0, 1.08fr) minmax(0, 2fr) max-content;
        align-items: center;
        gap: .55rem;
        margin: .35rem 0;
        font-size: .87rem;
    }
    .summary-row span { overflow-wrap: anywhere; }
    .summary-track { overflow: hidden; height: 1.1rem; border-radius: 1rem; background: #f2e8ec; }
    .summary-track div { height: 100%; }
    @media (max-width: 520px) {
        .summary-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) max-content; font-size: .8rem; }
    }
    </style>
    """)


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🍷", layout="centered")
    apply_styles()
    try:
        path = prepare_db(DB_PATH)
        settings = load_settings(path)
        if st.query_params.get("admin") == "1":
            render_admin(path, settings)
        else:
            render_tasting(path, settings)
    except sqlite3.Error:
        st.error("A wine_votes.db adatbázis most nem érhető el. Próbáld meg újra.")


if __name__ == "__main__":
    main()
