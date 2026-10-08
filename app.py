"""Design 1 – bordó-fehér borkóstoló, Streamlit >= 1.41.

Indítás: python -m streamlit run bor_kostolo_design1.py
Az eredeti wine_votes.db és az opcionális GEOTerroir_HUN.jpg maradjon
a programmal azonos mappában. Admin: ?admin=1, ADMIN_PASSWORD változó.
"""

import os
import sqlite3
import hashlib
import html
import inspect
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_TITLE = "Magyar borvidékek geológiája és kultúrája"
DB_PATH = Path(__file__).with_name("wine_votes.db")
LOGO_PATH = Path(__file__).with_name("GEOTerroir_HUN.jpg")
DEFAULT_WINE_COUNT = 5
MAX_WINE_COUNT = 50

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
        ("intenzitas", "Illat – intenzitás", ["Visszafogott", "Közepes", "Határozott"]),
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


def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    return c


def init_db():
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant TEXT NOT NULL,
                wine INTEGER NOT NULL DEFAULT 1,
                section TEXT NOT NULL,
                question TEXT NOT NULL,
                option TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        # Régi adatbázis automatikus frissítése: wine oszlop hozzáadása, ha még nincs.
        columns = [r[1] for r in c.execute("PRAGMA table_info(votes)").fetchall()]
        if "wine" not in columns:
            c.execute("ALTER TABLE votes ADD COLUMN wine INTEGER NOT NULL DEFAULT 1")
        c.execute("DROP INDEX IF EXISTS uq_vote")
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_wine "
            "ON votes(participant, wine, section, question, option)"
        )
        c.commit()


def get_setting(key, default=""):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key, value):
    with conn() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        c.commit()


def wine_name(wine):
    return get_setting(f"wine_{wine}_name", f"{wine}. tétel")


def wine_count():
    try:
        value = int(get_setting("wine_count", str(DEFAULT_WINE_COUNT)))
    except (TypeError, ValueError):
        value = DEFAULT_WINE_COUNT
    return max(1, min(value, MAX_WINE_COUNT))


WINE_TYPES = {
    "Fehér": (244, 241, 186),
    "Rozé": (245, 124, 131),
    "Vörös": (187, 34, 40),
}


def wine_type(wine):
    value = get_setting(f"wine_{wine}_type", "Fehér")
    return value if value in WINE_TYPES else "Fehér"


def wine_color(wine):
    r, g, b = WINE_TYPES[wine_type(wine)]
    return f"rgb({r}, {g}, {b})"


def participant_id():
    if "participant_id" not in st.session_state:
        seed = f"{time.time_ns()}-{os.urandom(16).hex()}"
        st.session_state.participant_id = hashlib.sha256(seed.encode()).hexdigest()[:20]
    return st.session_state.participant_id


def replace_single_vote(wine, section, question, option):
    pid = participant_id()
    with conn() as c:
        c.execute(
            "DELETE FROM votes WHERE participant=? AND wine=? AND section=? AND question=?",
            (pid, wine, section, question),
        )
        c.execute(
            "INSERT INTO votes(participant, wine, section, question, option, created_at) VALUES(?,?,?,?,?,?)",
            (pid, wine, section, question, option, datetime.utcnow().isoformat()),
        )
        c.commit()


def replace_multi_votes(wine, section, question, options):
    pid = participant_id()
    with conn() as c:
        c.execute(
            "DELETE FROM votes WHERE participant=? AND wine=? AND section=? AND question=?",
            (pid, wine, section, question),
        )
        for option in options:
            c.execute(
                "INSERT INTO votes(participant, wine, section, question, option, created_at) VALUES(?,?,?,?,?,?)",
                (pid, wine, section, question, option, datetime.utcnow().isoformat()),
            )
        c.commit()


def fetch_votes(wine=None, section=None, question=None):
    sql = "SELECT participant, wine, section, question, option, created_at FROM votes WHERE 1=1"
    params = []
    if wine is not None:
        sql += " AND wine=?"
        params.append(int(wine))
    if section:
        sql += " AND section=?"
        params.append(section)
    if question:
        sql += " AND question=?"
        params.append(question)
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


def result_table(wine, section, question, options=None, multi=False):
    df = fetch_votes(wine, section, question)
    if df.empty:
        return pd.DataFrame(columns=["Válasz", "Fő", "%"]), 0
    voters = df["participant"].nunique()
    counts = df.groupby("option")["participant"].nunique().sort_values(ascending=False)
    if options:
        counts = counts.reindex(options, fill_value=0)
    if multi:
        pct = counts / max(voters, 1) * 100
    else:
        total = counts.sum()
        pct = counts / max(total, 1) * 100
    out = pd.DataFrame({"Válasz": counts.index, "Fő": counts.values, "%": pct.round(1).values})
    return out, voters


def render_result_bars(wine, section, question, options=None, multi=False):
    table, voters = result_table(wine, section, question, options, multi)
    st.caption(f"Szavazók száma: {voters} fő")
    if table.empty:
        st.info("Még nincs szavazat.")
        return
    for _, row in table.iterrows():
        st.write(f"**{row['Válasz']}** — {row['%']:.1f}% · {int(row['Fő'])} fő")
        st.progress(min(float(row["%"])/100.0, 1.0))


def full_width_kwargs(widget):
    """Új Streamlit: width='stretch'; korábbi: use_container_width."""
    width = inspect.signature(widget).parameters.get("width")
    if width is not None and width.default in ("content", "stretch"):
        return {"width": "stretch"}
    return {"use_container_width": True}


def update_choice(state_key, option, multi):
    """A callback a kirajzolás előtt frissíti a kijelölést."""
    if multi:
        selected = list(st.session_state.get(state_key, []) or [])
        if option in selected:
            selected.remove(option)
        else:
            selected.append(option)
        st.session_state[state_key] = selected
    else:
        st.session_state[state_key] = option
    st.session_state[f"_changed_{state_key}"] = True


def choice_buttons(options, state_key, multi=False, columns=3, label_fn=None):
    """Fehér alapgombok; a kijelölés világossárga primary típusú."""
    if state_key not in st.session_state:
        st.session_state[state_key] = [] if multi else None
    selected = st.session_state[state_key]
    columns = max(1, columns)
    button_area = st.container(key=f"multi_{state_key}") if multi else st
    for start in range(0, len(options), columns):
        row_options = options[start:start + columns]
        cols = button_area.columns(columns, gap="small")
        for offset, option in enumerate(row_options):
            chosen = option in selected if multi else option == selected
            cols[offset].button(
                label_fn(option) if label_fn else str(option),
                key=f"btn_{state_key}_{start + offset}",
                type="primary" if chosen else "secondary",
                on_click=update_choice,
                args=(state_key, option, multi),
                **full_width_kwargs(st.button),
            )
    return st.session_state.pop(f"_changed_{state_key}", False)


def save_primary_aromas(wine, section_key, category_key, detail_keys):
    selected_categories = st.session_state.get(category_key, []) or []
    detailed = []
    for cat, key in detail_keys.items():
        vals = st.session_state.get(key, []) or []
        detailed.extend([f"{cat} → {v}" for v in vals])
    replace_multi_votes(wine, section_key, "elsodleges_aromak", selected_categories + detailed)


def primary_aroma_form(wine, section_key, title):
    st.subheader(title)
    category_key = f"w{wine}_{section_key}_primary_categories"
    detail_keys = {
        cat: f"w{wine}_{section_key}_{cat}"
        for cat in PRIMARY_AROMAS
    }
    st.markdown("**Aromacsoportok**")
    if choice_buttons(list(PRIMARY_AROMAS), category_key, multi=True, columns=5):
        save_primary_aromas(wine, section_key, category_key, detail_keys)
    for cat, options in PRIMARY_AROMAS.items():
        st.markdown(f"**{cat}**")
        if choice_buttons(options, detail_keys[cat], multi=True, columns=5):
            save_primary_aromas(wine, section_key, category_key, detail_keys)


def save_multi_aroma_votes(wine, section_key, data, widget_keys):
    selected = []
    for group in data:
        vals = st.session_state.get(widget_keys[group], []) or []
        selected.extend([f"{group} → {v}" for v in vals])
    replace_multi_votes(wine, section_key, "aromak", selected)


def multi_aroma_block(wine, section_key, data, title):
    st.subheader(title)
    widget_keys = {
        group: f"w{wine}_{section_key}_{group}"
        for group in data
    }
    for group, options in data.items():
        st.markdown(f"**{group}**")
        if choice_buttons(options, widget_keys[group], multi=True, columns=5):
            save_multi_aroma_votes(wine, section_key, data, widget_keys)


def scale_question(wine, section, qkey, label, options):
    st.markdown(f"### {label}")
    widget_key = f"choice_w{wine}_{section}_{qkey}"
    if choice_buttons(options, widget_key, multi=False, columns=min(4, len(options))):
        replace_single_vote(wine, section, qkey, st.session_state[widget_key])


def top_single_result(wine, section, qkey, options=None):
    table, voters = result_table(wine, section, qkey, options=options, multi=False)
    if table.empty or voters == 0:
        return None
    row = table.sort_values(["%", "Fő"], ascending=False).iloc[0]
    return {
        "label": str(row["Válasz"]),
        "pct": float(row["%"]),
        "count": int(row["Fő"]),
    }


def top_multi_results(wine, section, qkey, top_n=5):
    table, voters = result_table(wine, section, qkey, multi=True)
    if table.empty or voters == 0:
        return []
    # A részletes "Kategória → aroma" jelöléseket kihagyjuk a tömör összesítésből,
    # és csak a fő aromacsoportokat mutatjuk.
    table = table[~table["Válasz"].astype(str).str.contains("→", regex=False)]
    if table.empty:
        return []
    table = table.sort_values(["%", "Fő"], ascending=False).head(top_n)
    return [
        {
            "label": str(row["Válasz"]),
            "pct": float(row["%"]),
            "count": int(row["Fő"]),
        }
        for _, row in table.iterrows()
    ]


def fmt_pct(value):
    if abs(value - round(value)) < 0.05:
        return f"{int(round(value))}%"
    return f"{value:.1f}%".replace(".", ",")


def render_single_summary_chart(wine, section, qkey, label, options=None):
    table, voters = result_table(wine, section, qkey, options=options, multi=False)

    if table.empty or voters == 0:
        st.markdown(f"### {label}")
        st.caption("Még nincs szavazat.")
        return

    if options:
        order_map = {opt: i for i, opt in enumerate(options)}
        table = table.copy()
        table["_order"] = table["Válasz"].map(order_map).fillna(999)
        table = table.sort_values("_order")
    else:
        table = table.sort_values("%", ascending=False)

    fill_color = wine_color(wine)
    rows = []
    for _, row in table.iterrows():
        option = html.escape(str(row["Válasz"]))
        pct = float(row["%"])
        count = int(row["Fő"])
        pct_text = fmt_pct(pct)
        bar_width = pct if pct > 0 else 0
        rows.append(
            f'<div class="summary-row">'
            f'<div class="summary-option">{option}</div>'
            f'<div class="summary-track">'
            f'<div class="summary-fill" style="width:{bar_width:.1f}%;background:{fill_color}"></div>'
            f'</div>'
            f'<div class="summary-value">{pct_text} ({count} fő)</div>'
            f'</div>'
        )

    summary_html = (
        f'<div class="summary-question">'
        f'<div class="summary-question-title">{html.escape(label)}</div>'
        f'{"".join(rows)}'
        f'</div>'
    )
    st.markdown(summary_html, unsafe_allow_html=True)


def render_multi_summary_chart(wine, section, qkey, label, primary_groups=False, top_n=10):
    table, voters = result_table(wine, section, qkey, multi=True)

    if table.empty or voters == 0:
        st.markdown(f"### {label}")
        st.caption("Még nincs szavazat.")
        return

    table = table.copy()
    if primary_groups:
        table = table[~table["Válasz"].astype(str).str.contains("→", regex=False)]

    table = table[table["Fő"] > 0]
    if table.empty:
        st.markdown(f"### {label}")
        st.caption("Még nincs szavazat.")
        return

    table = table.sort_values(["%", "Fő"], ascending=False).head(top_n)
    fill_color = wine_color(wine)
    rows = []
    for _, row in table.iterrows():
        label_text = str(row["Válasz"]).replace(" → ", " – ")
        option = html.escape(label_text)
        pct = float(row["%"])
        count = int(row["Fő"])
        pct_text = fmt_pct(pct)
        rows.append(
            f'<div class="summary-row aroma-row">'
            f'<div class="summary-option">{option}</div>'
            f'<div class="summary-track">'
            f'<div class="summary-fill" style="width:{pct:.1f}%;background:{fill_color}"></div>'
            f'</div>'
            f'<div class="summary-value">{pct_text} ({count} fő)</div>'
            f'</div>'
        )

    summary_html = (
        f'<div class="summary-question">'
        f'<div class="summary-question-title">{html.escape(label)}</div>'
        f'{"".join(rows)}'
        f'</div>'
    )
    st.markdown(summary_html, unsafe_allow_html=True)


def render_single_summary_line(wine, section, qkey, label, options=None):
    result = top_single_result(wine, section, qkey, options=options)
    if result is None:
        st.markdown(f"**{label}** – még nincs szavazat")
        return
    st.markdown(
        f"**{label}** – {result['label']} "
        f"({fmt_pct(result['pct'])}, {result['count']} fő)"
    )


def render_multi_summary_line(wine, section, qkey, label, top_n=5):
    results = top_multi_results(wine, section, qkey, top_n=top_n)
    if not results:
        st.markdown(f"**{label}:** még nincs szavazat")
        return
    items = ", ".join(
        f"{r['label']} ({fmt_pct(r['pct'])}, {r['count']} fő)"
        for r in results
    )
    st.markdown(f"**{label}:** {items}")


def wine_summary(wine):
    st.header(wine_name(wine))
    st.caption(f"{wine_type(wine)}bor")
    wine_votes = fetch_votes(wine=wine)
    if wine_votes.empty:
        st.info("Ehhez a tételhez még nincs szavazat.")
        return

    st.markdown("## Illat")
    render_single_summary_chart(
        wine,
        "illat",
        "intenzitas",
        "Illat intenzitása",
        ["Visszafogott", "Közepes", "Határozott"],
    )
    render_multi_summary_chart(
        wine,
        "illat",
        "elsodleges_aromak",
        "Illat – elsődleges aromák",
        primary_groups=True,
        top_n=10,
    )

    st.markdown("## Ízösszetétel")
    for qkey, label, options in SCALE_QUESTIONS["iz"]:
        render_single_summary_chart(wine, "iz", qkey, label, options=options)

    render_multi_summary_chart(
        wine,
        "iz",
        "elsodleges_aromak",
        "Íz – elsődleges aromák",
        primary_groups=True,
        top_n=10,
    )

    st.markdown("## Másodlagos aromák")
    render_multi_summary_chart(
        wine,
        "masodlagos",
        "aromak",
        "Másodlagos aromák",
        top_n=10,
    )

    st.markdown("## Harmadlagos aromák")
    render_multi_summary_chart(
        wine,
        "harmadlagos",
        "aromak",
        "Harmadlagos aromák",
        top_n=10,
    )


@st.fragment(run_every="3s")
def live_summary_fragment(selected_summary_wine):
    wine_summary(selected_summary_wine)


def admin_panel():
    st.title("Admin")
    admin_pw = os.getenv("ADMIN_PASSWORD") or "boradmin26"
    if not admin_pw:
        st.error("Az ADMIN_PASSWORD környezeti változó nincs beállítva; az admin felület nem érhető el.")
        return
    pwd = st.text_input("Admin jelszó", type="password")
    if pwd != admin_pw:
        st.info("Add meg az admin jelszót.")
        return
    st.success("Admin mód aktív")

    tasting_name = st.text_input(
        "Kóstoló címe",
        value=get_setting("tasting_name", APP_TITLE),
    )

    st.markdown("### Tételek száma")
    current_count = wine_count()
    new_count = st.number_input(
        "Hány tétel legyen?",
        min_value=1,
        max_value=MAX_WINE_COUNT,
        value=current_count,
        step=1,
    )
    if st.button("Tételszám mentése", **full_width_kwargs(st.button)):
        set_setting("wine_count", int(new_count))
        st.success(f"Tételek száma: {int(new_count)}")
        st.rerun()

    st.markdown("### Tételek")
    names = {}
    types = {}
    for i in range(1, wine_count() + 1):
        with st.expander(f"{i}. tétel – {wine_name(i)}", expanded=(i <= 3)):
            names[i] = st.text_input(
                "Tétel neve",
                value=wine_name(i),
                key=f"admin_wine_{i}",
            )
            type_options = list(WINE_TYPES.keys())
            current_type = wine_type(i)
            st.markdown("**Bor típusa**")
            type_key = f"admin_wine_type_{i}"
            if type_key not in st.session_state:
                st.session_state[type_key] = current_type
            choice_buttons(type_options, type_key, columns=3)
            types[i] = st.session_state[type_key]

    if st.button("Tételek adatainak mentése", **full_width_kwargs(st.button)):
        set_setting("tasting_name", tasting_name)
        for i in range(1, wine_count() + 1):
            set_setting(f"wine_{i}_name", names[i].strip() or f"{i}. tétel")
            set_setting(f"wine_{i}_type", types[i])
        st.success("Mentve.")

    st.markdown("### Összesített adatok")
    df = fetch_votes()
    if df.empty:
        st.info("Még nincs szavazat.")
    else:
        export = df.copy()
        export.insert(
            2,
            "wine_name",
            export["wine"].map({i: wine_name(i) for i in range(1, wine_count() + 1)}),
        )
        export.insert(
            3,
            "wine_type",
            export["wine"].map({i: wine_type(i) for i in range(1, wine_count() + 1)}),
        )
        csv = export.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV letöltése",
            csv,
            file_name="wine_votes.csv",
            mime="text/csv",
        )

    st.markdown("### Eredmények tételek szerint")
    st.markdown("**Összesítés megtekintése – tétel**")
    if "admin_summary_wine" not in st.session_state:
        st.session_state.admin_summary_wine = 1
    choice_buttons(list(range(1, wine_count() + 1)), "admin_summary_wine", columns=3, label_fn=wine_name)
    summary_wine = st.session_state.admin_summary_wine
    live_summary_fragment(summary_wine)

    st.markdown("### Adatok törlése")
    st.markdown("**Törlendő tétel**")
    if "delete_wine" not in st.session_state:
        st.session_state.delete_wine = 1
    choice_buttons(list(range(1, wine_count() + 1)), "delete_wine", columns=3, label_fn=wine_name)
    delete_wine = st.session_state.delete_wine
    c1, c2 = st.columns(2)
    if c1.button("Kiválasztott tétel szavazatainak törlése", type="secondary", **full_width_kwargs(st.button)):
        with conn() as c:
            c.execute("DELETE FROM votes WHERE wine=?", (delete_wine,))
            c.commit()
        st.warning(f"{wine_name(delete_wine)} szavazatai törölve.")

    if c2.button("MINDEN SZAVAZAT TÖRLÉSE", type="secondary", **full_width_kwargs(st.button)):
        with conn() as c:
            c.execute("DELETE FROM votes")
            c.commit()
        st.warning("Minden szavazat törölve.")


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🍷", layout="centered")
    init_db()
    st.markdown(
        """
        <style>
        :root {
            --wine: #7b2341;
            --wine-dark: #601a32;
            --wine-border: #e5cdd5;
            --wine-ink: #35252c;
            --selected: rgb(244, 241, 186);
            --selected-border: #d5ce86;
        }
        [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background: #fcf9fa;
            color: var(--wine-ink);
            color-scheme: light;
        }
        .block-container {
            max-width: 960px;
            padding-top: 2rem;
            padding-bottom: 5rem;
        }
        .main-title {
            color: var(--wine);
            font-size: clamp(1.65rem, 5vw, 2.8rem);
            line-height: 1.16;
            margin: 0 0 1rem;
            padding: 0;
            font-weight: 800;
            letter-spacing: -0.035em;
        }
        [data-testid="stHeading"] h1,
        [data-testid="stHeading"] h2,
        [data-testid="stHeading"] h3 { color: var(--wine); }
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"] { color: var(--wine-ink); }
        [data-testid="stCaptionContainer"] { color: #78636c; }
        hr { border-color: #eadce1; margin: 1.8rem 0; }

        /* A primary/secondary állapotot Python vezérli, nem CSS :active. */
        .stButton button,
        [data-testid="stButton"] button,
        [data-testid="stDownloadButton"] button {
            min-height: 3.15rem;
            height: auto;
            padding: 0.7rem 1rem;
            border: 1px solid var(--wine-border) !important;
            border-radius: 16px;
            background: #ffffff !important;
            color: var(--wine) !important;
            font-weight: 600;
            box-shadow: 0 3px 10px rgba(74, 24, 44, 0.08);
            white-space: normal;
            overflow-wrap: anywhere;
            transition: background-color 150ms ease, box-shadow 150ms ease,
                        border-color 150ms ease;
        }
        .stButton button p,
        [data-testid="stButton"] button p,
        [data-testid="stDownloadButton"] button p { color: inherit !important; }
        .stButton button[kind="primary"],
        [data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
            background: var(--selected) !important;
            border-color: var(--selected-border) !important;
            color: var(--wine-ink) !important;
            box-shadow: 0 5px 14px rgba(131, 122, 50, 0.16);
        }
        .stButton button[kind="secondary"]:hover,
        [data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stDownloadButton"] button:hover {
            background: #f9edf1 !important;
            border-color: var(--wine) !important;
            box-shadow: 0 5px 14px rgba(74, 24, 44, 0.12);
        }
        .stButton button[kind="primary"]:hover,
        [data-testid="stButton"] button[data-testid="stBaseButton-primary"]:hover {
            background: var(--selected) !important;
            border-color: #aaa158 !important;
        }
        [class*="st-key-multi_"] [data-testid="stButton"] button {
            min-height: 2.5rem;
            padding: 0.4rem 0.5rem;
            border-radius: 12px;
        }
        [class*="st-key-multi_"] [data-testid="stButton"] button p {
            font-size: 0.85rem;
            line-height: 1.25;
        }
        .stButton button:focus-visible,
        [data-testid="stButton"] button:focus-visible,
        [data-testid="stDownloadButton"] button:focus-visible {
            outline: 3px solid #ba6d86 !important;
            outline-offset: 3px;
        }
        [data-testid="stExpander"] {
            border: 1px solid #eadce1;
            border-radius: 16px;
            background: #ffffff;
            box-shadow: 0 3px 12px rgba(74, 24, 44, 0.04);
        }
        [data-testid="stMetricValue"] { font-size: 2rem; color: var(--wine); }
        [data-testid="stProgress"] [role="progressbar"] > div > div {
            background-color: var(--wine);
        }
        @media (prefers-reduced-motion: reduce) {
            .stButton button, [data-testid="stDownloadButton"] button {
                transition: none;
            }
        }

        /* Tömör, referenciaábrához hasonló összesítő */
        .summary-question {
            margin: 0.4rem 0 1.2rem 0;
        }
        .summary-question-title {
            font-size: 1.05rem;
            font-weight: 800;
            margin: 0 0 0.35rem 0;
        }
        .summary-row {
            display: grid;
            grid-template-columns: minmax(90px, 0.9fr) minmax(150px, 2.2fr) minmax(88px, auto);
            align-items: center;
            gap: 0.55rem;
            margin: 0.28rem 0;
        }
        .summary-option {
            font-size: 0.88rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .aroma-row .summary-option {
            font-size: 0.80rem;
        }
        .summary-track {
            width: 100%;
            height: 18px;
            background: #f2e8ec;
            border: 1px solid #dac3cc;
            border-radius: 9px;
            box-sizing: border-box;
            overflow: hidden;
        }
        .summary-fill {
            height: 100%;
            box-sizing: border-box;
        }
        .summary-value {
            font-size: 0.86rem;
            font-weight: 700;
            white-space: nowrap;
            text-align: left;
        }
        @media (max-width: 640px) {
            .summary-row {
                grid-template-columns: 82px minmax(100px, 1fr) 82px;
                gap: 0.35rem;
            }
            .summary-option, .summary-value {
                font-size: 0.74rem;
            }
            .summary-track {
                height: 16px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    params = st.query_params
    if params.get("admin") == "1":
        admin_panel()
        return

    tasting_name = get_setting("tasting_name", APP_TITLE)

    header_logo, header_title = st.columns([1.25, 3.75], vertical_alignment="center")
    with header_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), **full_width_kwargs(st.image))
    with header_title:
        st.markdown(f"<h1 class='main-title'>{html.escape(tasting_name)}</h1>", unsafe_allow_html=True)

    st.markdown("**Melyik tételt értékeled?**")
    if "active_wine" not in st.session_state:
        st.session_state.active_wine = 1
    choice_buttons(
        list(range(1, wine_count() + 1)),
        "active_wine",
        columns=3,
        label_fn=wine_name,
    )
    wine = st.session_state.active_wine
    if wine > wine_count():
        wine = 1
        st.session_state.active_wine = wine

    st.caption("Válaszd ki a tételt, majd jelöld a megfelelő jellemzőket. A válaszok automatikusan mentésre kerülnek.")

    st.header("Illat")
    scale_question(wine, "illat", "intenzitas", "Illat – intenzitás", ["Visszafogott", "Közepes", "Határozott"])
    st.divider()
    primary_aroma_form(wine, "illat", "Illat – elsődleges aromák")

    st.divider()
    st.header("Ízösszetétel")
    for qkey, label, options in SCALE_QUESTIONS["iz"]:
        scale_question(wine, "iz", qkey, label, options)
        st.divider()
    primary_aroma_form(wine, "iz", "Íz – elsődleges aromák")

    st.divider()
    multi_aroma_block(wine, "masodlagos", SECONDARY_AROMAS, "Másodlagos aromák")

    st.divider()
    multi_aroma_block(wine, "harmadlagos", TERTIARY_AROMAS, "Harmadlagos aromák")

    st.divider()
    st.caption("Geoterroir Kutatócsoport")


if __name__ == "__main__":
    main()
