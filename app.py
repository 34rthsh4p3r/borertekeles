# -*- coding: utf-8 -*-
"""
Magyar borvidékek geológiája és kultúrája – borkóstoló közönségszavazás.

Futtatás:
    pip install -r requirements.txt
    streamlit run app.py

Admin felület: ?admin=1 (jelszó: ADMIN_PASSWORD környezeti változó / secret,
fejlesztési tartalék: boradmin26)
"""

import base64
import hashlib
import hmac
import html
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Konstansok
# ---------------------------------------------------------------------------

APP_TITLE = "Magyar borvidékek geológiája és kultúrája"
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "GEOTerroir_HUN.jpg"
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "borkostolo.db"))
DEFAULT_ADMIN_PASSWORD = "boradmin26"

MIN_WINES, MAX_WINES, DEFAULT_WINES = 1, 50, 5
DEFAULT_WINE_NAME = "Bortétel"

WINE_TYPES = ["Fehér", "Rozé", "Vörös"]
WINE_TYPE_LABELS = {"Fehér": "Fehérbor", "Rozé": "Rozébor", "Vörös": "Vörösbor"}
WINE_COLORS = {
    "Fehér": "rgb(244, 241, 186)",
    "Rozé": "rgb(245, 124, 131)",
    "Vörös": "rgb(187, 34, 40)",
}
NEUTRAL_COLOR = "rgb(184, 184, 184)"
ARROW = " → "

# Illat
SMELL_SECTION = "illat"
SMELL_SCALES = [
    ("intenzitas", "Illat intenzitása", ["Visszafogott", "Közepes", "Határozott"]),
]

# Ízösszetétel
TASTE_SCALE_SECTION = "izosszetetel"
TASTE_SCALES = [
    ("edesseg", "Édesség", ["Száraz", "Félszáraz", "Félédes", "Édes"]),
    ("savassag", "Savasság", ["Alacsony", "Közepes", "Magas"]),
    ("tannin", "Tannin", ["Alacsony", "Közepes", "Magas"]),
    ("alkohol", "Alkohol", ["Alacsony", "Közepes", "Magas"]),
    ("testesseg", "Testesség", ["Könnyű", "Közepes", "Telt"]),
    ("intenzitas", "Intenzitás", ["Könnyű", "Közepes", "Határozott"]),
    ("lecsengese", "Lecsengés", ["Rövid", "Közepes", "Hosszú"]),
]
TANNIN_KEY = "tannin"

TASTE_AROMA_SECTION = "iz"
PRIMARY_QUESTION = "elsodleges_aromak"
SECONDARY_SECTION = "masodlagos"
TERTIARY_SECTION = "harmadlagos"
GROUP_QUESTION = "aromak"

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
        "vanília", "szegfűszeg", "szerecsendió", "kókusz", "karamella", "pirítós",
        "égett fa", "füst", "csokoládé", "kávé", "gyanta", "cédrus",
    ],
}

TERTIARY_AROMAS = {
    "Oxidáció": ["mandula", "mogyoró", "dió", "csokoládé", "kávé", "karamell"],
    "Vörösbor": [
        "szárított gyümölcs", "bőr", "föld", "gomba", "erdei talaj", "hús",
        "dohány", "nedves levél", "karamell",
    ],
    "Fehérbor": [
        "szárított gyümölcs", "narancslekvár", "petrol (benzin)", "fahéj",
        "gyömbér", "szerecsendió", "mogyoró", "méz", "karamell",
    ],
}

GROUPS_BY_SECTION = {
    SECONDARY_SECTION: SECONDARY_AROMAS,
    TERTIARY_SECTION: TERTIARY_AROMAS,
}

CSS = "".join([
    ".block-container{max-width:880px;padding-top:1.2rem;padding-left:1rem;padding-right:1rem}",
    ".apphead{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;margin-bottom:.4rem}",
    ".apptitle{flex:1 1 260px;font-size:1.7rem;line-height:1.2;font-weight:700;margin:0}",
    ".applogo{height:auto;max-height:72px;max-width:100%;object-fit:contain}",
    ".tastingtitle{opacity:.75;margin-bottom:.5rem}",
    'div[data-testid="stRadio"] label{min-height:44px;align-items:center}',
    ".stButton>button,.stDownloadButton>button{min-height:44px}",
    ".wtitle{font-size:2rem;font-weight:800;line-height:1.15;margin-top:.3rem}",
    ".wsub{font-size:.95rem;opacity:.7;margin-bottom:.6rem}",
    ".qtitle{font-weight:700;margin:14px 0 4px}",
    ".vempty{opacity:.6;font-size:.9rem;margin:4px 0}",
    ".vrow{display:grid;grid-template-columns:90px 1fr auto;gap:8px;align-items:center;margin:5px 0}",
    ".vrow.wide{grid-template-columns:150px 1fr auto}",
    ".vlabel{font-size:.85rem;font-weight:600;text-transform:uppercase;overflow-wrap:anywhere}",
    ".vtrack{background:rgba(128,128,128,.14);border-radius:4px;height:20px}",
    ".vbar{height:100%;box-sizing:border-box;border-radius:4px}",
    ".vval{font-size:.85rem;white-space:nowrap;text-align:right}",
    "@media (max-width:600px){",
    ".apptitle{font-size:1.35rem}",
    ".applogo{max-height:56px}",
    ".wtitle{font-size:1.6rem}",
    ".vrow{grid-template-columns:82px minmax(100px,1fr) 82px;gap:6px}",
    ".vrow.wide{grid-template-columns:110px minmax(80px,1fr) 64px}",
    ".vlabel{font-size:.72rem}",
    ".vval{font-size:.75rem;white-space:normal;line-height:1.1}",
    "}",
])


# ---------------------------------------------------------------------------
# Adatbázis és beállítások
# ---------------------------------------------------------------------------

def conn() -> sqlite3.Connection:
    """Új SQLite kapcsolat WAL móddal."""
    connection = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA busy_timeout=30000;")
    return connection


@st.cache_resource
def init_db() -> bool:
    """Táblák és indexek létrehozása (folyamatonként egyszer)."""
    with closing(conn()) as connection, connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS votes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "participant TEXT NOT NULL,"
            "wine INTEGER NOT NULL,"
            "section TEXT NOT NULL,"
            "question TEXT NOT NULL,"
            "option TEXT NOT NULL,"
            "created_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_votes_unique "
            "ON votes(participant, wine, section, question, option)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS ix_votes_wine ON votes(wine)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
    return True


def get_setting(key: str, default=None):
    with closing(conn()) as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row[0] if row else default


def set_setting(key: str, value) -> None:
    set_many_settings({key: value})


def set_many_settings(values: dict) -> None:
    with closing(conn()) as connection, connection:
        connection.executemany(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(k, str(v)) for k, v in values.items()],
        )


def wine_count() -> int:
    try:
        count = int(get_setting("wine_count", DEFAULT_WINES))
    except (TypeError, ValueError):
        count = DEFAULT_WINES
    return max(MIN_WINES, min(MAX_WINES, count))


def wine_name(wine: int) -> str:
    name = (get_setting(f"wine_{wine}_name", "") or "").strip()
    return name or DEFAULT_WINE_NAME


def wine_type(wine: int) -> str:
    stored = get_setting(f"wine_{wine}_type", "Fehér")
    return stored if stored in WINE_TYPES else "Fehér"


def wine_color(wine: int) -> str:
    return WINE_COLORS[wine_type(wine)]


# ---------------------------------------------------------------------------
# Résztvevő és szavazatok
# ---------------------------------------------------------------------------

def participant_id() -> str:
    """Anonim, session-önkénti azonosító."""
    if "participant_id" not in st.session_state:
        raw = os.urandom(32) + str(time.time_ns()).encode("utf-8")
        st.session_state["participant_id"] = hashlib.sha256(raw).hexdigest()[:32]
    return st.session_state["participant_id"]


def replace_multi_votes(participant: str, wine: int, section: str,
                        question: str, options: list) -> None:
    """Egy kérdés összes korábbi szavazatának cseréje az újakra."""
    unique_options = list(dict.fromkeys(options))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(conn()) as connection, connection:
        connection.execute(
            "DELETE FROM votes WHERE participant=? AND wine=? AND section=? AND question=?",
            (participant, wine, section, question),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO votes"
            "(participant, wine, section, question, option, created_at) "
            "VALUES(?,?,?,?,?,?)",
            [(participant, wine, section, question, opt, now) for opt in unique_options],
        )


def replace_single_vote(participant: str, wine: int, section: str,
                        question: str, option: str) -> None:
    replace_multi_votes(participant, wine, section, question, [option])


def my_votes(participant: str, wine: int) -> dict:
    """A résztvevő saját szavazatai: {(section, question): [option, ...]}."""
    with closing(conn()) as connection:
        rows = connection.execute(
            "SELECT section, question, option FROM votes WHERE participant=? AND wine=?",
            (participant, wine),
        ).fetchall()
    result: dict = {}
    for section, question, option in rows:
        result.setdefault((section, question), []).append(option)
    return result


def fetch_votes(wine: int) -> pd.DataFrame:
    with closing(conn()) as connection:
        return pd.read_sql_query(
            "SELECT participant, wine, section, question, option, created_at "
            "FROM votes WHERE wine = ? ORDER BY id",
            connection,
            params=(wine,),
        )


def delete_votes(wine: int | None = None) -> None:
    with closing(conn()) as connection, connection:
        if wine is None:
            connection.execute("DELETE FROM votes")
        else:
            connection.execute("DELETE FROM votes WHERE wine = ?", (wine,))


def votes_csv() -> bytes:
    with closing(conn()) as connection:
        df = pd.read_sql_query(
            "SELECT participant, wine, section, question, option, created_at "
            "FROM votes ORDER BY wine, participant, id",
            connection,
        )
    df.insert(2, "wine_name", df["wine"].map(wine_name))
    df.insert(3, "wine_type", df["wine"].map(wine_type))
    return df.to_csv(index=False).encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Eredményszámítás
# ---------------------------------------------------------------------------

def result_table(votes: pd.DataFrame, section: str, question: str,
                 options: list | None = None, multi: bool = False,
                 main_only: bool = False) -> pd.DataFrame:
    """
    Single choice: Válasz, Fő, Százalék (az összes leadott szavazat arányában).
    Multi choice: Válasz, Fő (százalék nélkül), csak legalább 1 szavazatot kapott elemek.
    """
    subset = votes[(votes["section"] == section) & (votes["question"] == question)]
    if main_only:
        subset = subset[~subset["option"].str.contains(ARROW, regex=False)]
    counts = subset.groupby("option")["participant"].nunique()

    if multi:
        counts = counts[counts > 0].sort_values(ascending=False, kind="stable")
        return pd.DataFrame({"Válasz": list(counts.index), "Fő": [int(v) for v in counts.values]})

    option_list = options if options is not None else list(counts.index)
    total = int(counts.sum())
    rows = []
    for option in option_list:
        count = int(counts.get(option, 0))
        pct = (count / total * 100) if total else 0.0
        rows.append((option, count, pct))
    return pd.DataFrame(rows, columns=["Válasz", "Fő", "Százalék"])


def respondent_count(votes: pd.DataFrame, section: str, question: str) -> int:
    subset = votes[(votes["section"] == section) & (votes["question"] == question)]
    return int(subset["participant"].nunique())


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------

def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()


@st.cache_data
def logo_base64() -> str:
    if LOGO_PATH.exists():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return ""


def inject_css() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def render_header() -> None:
    encoded_logo = logo_base64()
    logo_html = ""
    if encoded_logo:
        logo_html = (
            f'<img class="applogo" src="data:image/jpeg;base64,{encoded_logo}" '
            'alt="GeoTerroir Kutatócsoport logó">'
        )
    st.markdown(
        f'<div class="apphead"><div class="apptitle">{esc(APP_TITLE)}</div>{logo_html}</div>',
        unsafe_allow_html=True,
    )
    tasting_title = (get_setting("tasting_title", "") or "").strip()
    if tasting_title:
        st.markdown(f'<div class="tastingtitle">{esc(tasting_title)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Szavazófelület: callbackek
# ---------------------------------------------------------------------------

def save_single_vote(wine: int, section: str, question: str, widget_key: str) -> None:
    value = st.session_state.get(widget_key)
    if value is not None:
        replace_single_vote(participant_id(), wine, section, question, value)


def primary_main_key(wine: int, section: str) -> str:
    return f"aroma_main_w{wine}_{section}"


def primary_detail_key(wine: int, section: str, main: str) -> str:
    return f"aroma_det_w{wine}_{section}_{slug(main)}"


def save_primary_aromas(wine: int, section: str) -> None:
    selected_mains = st.session_state.get(primary_main_key(wine, section), [])
    options = []
    for main, details in PRIMARY_AROMAS.items():
        if main not in selected_mains:
            continue
        options.append(main)
        chosen = st.session_state.get(primary_detail_key(wine, section, main), [])
        options.extend(f"{main}{ARROW}{d}" for d in details if d in chosen)
    replace_multi_votes(participant_id(), wine, section, PRIMARY_QUESTION, options)


def group_key(wine: int, section: str, group: str) -> str:
    return f"aroma_grp_w{wine}_{section}_{slug(group)}"


def save_group_aromas(wine: int, section: str) -> None:
    options = []
    for group, items in GROUPS_BY_SECTION[section].items():
        chosen = st.session_state.get(group_key(wine, section, group), [])
        options.extend(f"{group}{ARROW}{i}" for i in items if i in chosen)
    replace_multi_votes(participant_id(), wine, section, GROUP_QUESTION, options)


# ---------------------------------------------------------------------------
# Szavazófelület: widgetek
# ---------------------------------------------------------------------------

def scale_question(wine: int, section: str, question_key: str, label: str,
                   options: list, mine: dict) -> None:
    saved = mine.get((section, question_key), [])
    index = options.index(saved[0]) if saved and saved[0] in options else None
    widget_key = f"radio_w{wine}_{section}_{question_key}"
    st.radio(
        label,
        options,
        index=index,
        horizontal=True,
        key=widget_key,
        on_change=save_single_vote,
        args=(wine, section, question_key, widget_key),
    )


def primary_aroma_form(wine: int, section: str, mine: dict) -> None:
    saved = mine.get((section, PRIMARY_QUESTION), [])
    saved_mains = [m for m in PRIMARY_AROMAS if m in saved]
    selected = st.multiselect(
        "Aromakategóriák",
        list(PRIMARY_AROMAS),
        default=saved_mains,
        key=primary_main_key(wine, section),
        placeholder="Válassz kategóriát",
        on_change=save_primary_aromas,
        args=(wine, section),
    )
    for main, details in PRIMARY_AROMAS.items():
        if main not in selected:
            continue
        saved_details = [d for d in details if f"{main}{ARROW}{d}" in saved]
        with st.expander(f"{main} – részletes aromák", expanded=True):
            st.multiselect(
                f"{main} – részletek",
                details,
                default=saved_details,
                key=primary_detail_key(wine, section, main),
                placeholder="Válassz konkrét aromát",
                label_visibility="collapsed",
                on_change=save_primary_aromas,
                args=(wine, section),
            )


def multi_aroma_block(wine: int, section: str, groups: dict, mine: dict) -> None:
    saved = set(mine.get((section, GROUP_QUESTION), []))
    for group, items in groups.items():
        default = [i for i in items if f"{group}{ARROW}{i}" in saved]
        st.multiselect(
            group,
            items,
            default=default,
            key=group_key(wine, section, group),
            placeholder="Válassz",
            on_change=save_group_aromas,
            args=(wine, section),
        )


# ---------------------------------------------------------------------------
# Összesítő diagramok
# ---------------------------------------------------------------------------

def bar_row(label: str, fill: str, width_pct: float, right_text: str, wide: bool = False) -> str:
    width = max(0.0, min(100.0, width_pct))
    border = "border:1px solid #000;" if width > 0 else ""
    row_class = "vrow wide" if wide else "vrow"
    return (
        f'<div class="{row_class}"><div class="vlabel">{esc(label)}</div>'
        f'<div class="vtrack"><div class="vbar" style="width:{width:.2f}%;'
        f'background:{fill};{border}"></div></div>'
        f'<div class="vval">{esc(right_text)}</div></div>'
    )


def render_single_summary_chart(title: str, table: pd.DataFrame, color: str) -> None:
    parts = [f'<div class="qtitle">{esc(title)}</div>']
    if table.empty or int(table["Fő"].sum()) == 0:
        parts.append('<div class="vempty">Még nincs szavazat.</div>')
    else:
        max_pct = float(table["Százalék"].max())
        for answer, count, pct in zip(table["Válasz"], table["Fő"], table["Százalék"]):
            is_winner = abs(pct - max_pct) < 0.05
            fill = color if is_winner else NEUTRAL_COLOR
            parts.append(bar_row(answer, fill, pct, f"{pct:.0f}% ({count} fő)"))
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_multi_summary_chart(title: str, table: pd.DataFrame, color: str,
                               respondents: int) -> None:
    parts = [f'<div class="qtitle">{esc(title)}</div>']
    if table.empty or respondents == 0:
        parts.append('<div class="vempty">Még nincs szavazat.</div>')
    else:
        for answer, count in zip(table["Válasz"], table["Fő"]):
            width = count / respondents * 100
            parts.append(bar_row(answer, color, width, f"{count} fő", wide=True))
    st.markdown("".join(parts), unsafe_allow_html=True)


def wine_summary(wine: int) -> None:
    votes = fetch_votes(wine)
    color = wine_color(wine)
    type_name = wine_type(wine)

    st.markdown(
        f'<div class="wtitle">{esc(wine_name(wine))}</div>'
        f'<div class="wsub">{WINE_TYPE_LABELS[type_name]}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Szavazók száma ennél a tételnél: {int(votes['participant'].nunique())}")

    st.subheader("Illat")
    for question_key, label, options in SMELL_SCALES:
        table = result_table(votes, SMELL_SECTION, question_key, options=options)
        render_single_summary_chart(label, table, color)
    render_multi_summary_chart(
        "Illat – elsődleges aromák",
        result_table(votes, SMELL_SECTION, PRIMARY_QUESTION, multi=True, main_only=True),
        color,
        respondent_count(votes, SMELL_SECTION, PRIMARY_QUESTION),
    )

    st.subheader("Ízösszetétel")
    for question_key, label, options in TASTE_SCALES:
        if question_key == TANNIN_KEY and type_name == "Fehér":
            continue
        table = result_table(votes, TASTE_SCALE_SECTION, question_key, options=options)
        render_single_summary_chart(label, table, color)
    render_multi_summary_chart(
        "Íz – elsődleges aromák",
        result_table(votes, TASTE_AROMA_SECTION, PRIMARY_QUESTION, multi=True, main_only=True),
        color,
        respondent_count(votes, TASTE_AROMA_SECTION, PRIMARY_QUESTION),
    )
    render_multi_summary_chart(
        "Másodlagos aromák",
        result_table(votes, SECONDARY_SECTION, GROUP_QUESTION, multi=True),
        color,
        respondent_count(votes, SECONDARY_SECTION, GROUP_QUESTION),
    )
    render_multi_summary_chart(
        "Harmadlagos aromák",
        result_table(votes, TERTIARY_SECTION, GROUP_QUESTION, multi=True),
        color,
        respondent_count(votes, TERTIARY_SECTION, GROUP_QUESTION),
    )


@st.fragment(run_every="3s")
def live_summary_fragment(wine: int) -> None:
    """Kb. 3 másodpercenként újraolvassa az adatbázist."""
    wine_summary(wine)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def expected_admin_password() -> str:
    env_value = os.environ.get("ADMIN_PASSWORD")
    if env_value:
        return env_value
    try:
        secret_value = st.secrets["ADMIN_PASSWORD"]
        if secret_value:
            return str(secret_value)
    except Exception:
        pass
    return DEFAULT_ADMIN_PASSWORD


def admin_panel() -> None:
    st.markdown("### Admin felület")

    if not st.session_state.get("admin_ok"):
        candidate = st.text_input("Admin jelszó", type="password", key="admin_pw_input")
        if st.button("Belépés", key="admin_login_button"):
            if hmac.compare_digest(candidate.encode("utf-8"),
                                   expected_admin_password().encode("utf-8")):
                st.session_state["admin_ok"] = True
                st.rerun()
            else:
                st.error("Hibás jelszó.")
        return

    st.markdown("#### Kóstoló beállításai")
    title = st.text_input(
        "Kóstoló címe", value=get_setting("tasting_title", "") or "", key="admin_title"
    )
    count = int(st.number_input(
        "Hány tétel legyen?", min_value=MIN_WINES, max_value=MAX_WINES,
        value=wine_count(), step=1, key="admin_wine_count",
    ))

    new_names, new_types = {}, {}
    for i in range(1, count + 1):
        name_col, type_col = st.columns([3, 2])
        with name_col:
            new_names[i] = st.text_input(
                f"{i}. tétel neve",
                value=(get_setting(f"wine_{i}_name", "") or ""),
                placeholder=DEFAULT_WINE_NAME,
                key=f"admin_name_{i}",
            )
        with type_col:
            new_types[i] = st.selectbox(
                f"{i}. tétel típusa",
                WINE_TYPES,
                index=WINE_TYPES.index(wine_type(i)),
                key=f"admin_type_{i}",
            )

    if st.button("Beállítások mentése", type="primary", key="admin_save"):
        values = {"tasting_title": title.strip(), "wine_count": count}
        for i in range(1, count + 1):
            values[f"wine_{i}_name"] = new_names[i].strip()
            values[f"wine_{i}_type"] = new_types[i]
        set_many_settings(values)
        st.success("A beállítások mentve.")

    st.divider()
    st.markdown("#### Szavazatok exportja")
    st.download_button(
        "Szavazatok letöltése (CSV)",
        data=votes_csv(),
        file_name="szavazatok.csv",
        mime="text/csv",
        key="admin_csv",
    )

    st.divider()
    st.markdown("#### Szavazatok törlése")
    current_count = wine_count()
    wine_to_clear = st.selectbox(
        "Törlendő tétel",
        list(range(1, current_count + 1)),
        format_func=lambda i: f"{i}. {wine_name(i)}",
        key="admin_clear_wine",
    )
    confirm_one = st.checkbox("Biztosan törlöm a kiválasztott tétel összes szavazatát",
                              key="admin_confirm_one")
    if st.button("Tétel szavazatainak törlése", key="admin_clear_one", disabled=not confirm_one):
        delete_votes(wine_to_clear)
        st.success(f"A(z) {wine_to_clear}. tétel szavazatai törölve.")

    confirm_all = st.checkbox("Biztosan törlöm az ÖSSZES szavazatot", key="admin_confirm_all")
    if st.button("Minden szavazat törlése", key="admin_clear_all", disabled=not confirm_all):
        delete_votes(None)
        st.success("Minden szavazat törölve.")

    st.divider()
    st.markdown("#### Élő összesítés")
    preview_wine = st.selectbox(
        "Tétel",
        list(range(1, current_count + 1)),
        format_func=lambda i: f"{i}. {wine_name(i)}",
        key="admin_preview_wine",
    )
    live_summary_fragment(preview_wine)


# ---------------------------------------------------------------------------
# Főprogram
# ---------------------------------------------------------------------------

def voting_interface() -> None:
    total = wine_count()
    if st.session_state.get("active_wine", 1) > total:
        st.session_state["active_wine"] = 1

    wine = st.selectbox(
        "Melyik tételt értékeled?",
        list(range(1, total + 1)),
        format_func=lambda i: f"{i}. {wine_name(i)}",
        key="active_wine",
    )
    type_name = wine_type(wine)
    mine = my_votes(participant_id(), wine)

    tab_smell, tab_taste, tab_summary = st.tabs(["Illat", "Ízösszetétel", "Összesítés"])

    with tab_smell:
        for question_key, label, options in SMELL_SCALES:
            scale_question(wine, SMELL_SECTION, question_key, label, options, mine)
        st.markdown("**Elsődleges aromák**")
        primary_aroma_form(wine, SMELL_SECTION, mine)

    with tab_taste:
        for question_key, label, options in TASTE_SCALES:
            if question_key == TANNIN_KEY and type_name == "Fehér":
                continue
            scale_question(wine, TASTE_SCALE_SECTION, question_key, label, options, mine)
        st.markdown("**Elsődleges aromák**")
        primary_aroma_form(wine, TASTE_AROMA_SECTION, mine)
        st.markdown("**Másodlagos aromák**")
        multi_aroma_block(wine, SECONDARY_SECTION, SECONDARY_AROMAS, mine)
        st.markdown("**Harmadlagos aromák**")
        multi_aroma_block(wine, TERTIARY_SECTION, TERTIARY_AROMAS, mine)

    with tab_summary:
        live_summary_fragment(wine)


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🍷", layout="centered")
    init_db()
    inject_css()
    render_header()

    if str(st.query_params.get("admin", "")) == "1":
        admin_panel()
    else:
        voting_interface()


if __name__ == "__main__":
    main()
