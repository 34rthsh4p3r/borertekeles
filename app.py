import os
import sqlite3
import hashlib
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_TITLE = "A borok értékelése"
DB_PATH = Path(__file__).with_name("wine_votes.db")
WINE_COUNT = 5

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


def primary_aroma_form(wine, section_key, title):
    st.subheader(title)
    selected_categories = st.multiselect(
        "Mely elsődleges aromacsoportokat érzed?",
        list(PRIMARY_AROMAS.keys()),
        key=f"w{wine}_{section_key}_primary_categories",
    )
    detailed = []
    for cat in selected_categories:
        with st.expander(cat, expanded=True):
            vals = st.multiselect(
                "Konkrét aromák",
                PRIMARY_AROMAS[cat],
                key=f"w{wine}_{section_key}_{cat}",
            )
            detailed.extend([f"{cat} → {v}" for v in vals])
    if st.button("Elsődleges aromák mentése", key=f"save_w{wine}_{section_key}_primary", use_container_width=True):
        replace_multi_votes(wine, section_key, "elsodleges_aromak", selected_categories + detailed)
        st.success("Szavazat elmentve.")

    with st.expander("Élő eredmények", expanded=False):
        render_result_bars(wine, section_key, "elsodleges_aromak", multi=True)


def multi_aroma_block(wine, section_key, data, title):
    st.subheader(title)
    selected = []
    for group, options in data.items():
        vals = st.multiselect(group, options, key=f"w{wine}_{section_key}_{group}")
        selected.extend([f"{group} → {v}" for v in vals])
    if st.button("Aromák mentése", key=f"save_w{wine}_{section_key}", use_container_width=True):
        replace_multi_votes(wine, section_key, "aromak", selected)
        st.success("Szavazat elmentve.")
    with st.expander("Élő eredmények", expanded=False):
        render_result_bars(wine, section_key, "aromak", multi=True)


def scale_question(wine, section, qkey, label, options):
    st.markdown(f"### {label}")
    choice = st.radio(
        "Válassz:", options, horizontal=True,
        key=f"radio_w{wine}_{section}_{qkey}", label_visibility="collapsed"
    )
    if st.button("Szavazok", key=f"vote_w{wine}_{section}_{qkey}", use_container_width=True):
        replace_single_vote(wine, section, qkey, choice)
        st.success("Szavazat elmentve.")
    with st.expander("Élő eredmények", expanded=False):
        render_result_bars(wine, section, qkey, options=options, multi=False)


def chart_for_question(wine, section, qkey, label, options=None, multi=False, top_n=None):
    table, voters = result_table(wine, section, qkey, options=options, multi=multi)
    if table.empty or voters == 0:
        return
    if top_n:
        table = table.sort_values("%", ascending=False).head(top_n)
    chart_data = table.set_index("Válasz")[["%"]]
    st.markdown(f"**{label}** · {voters} fő")
    st.bar_chart(chart_data, horizontal=True, height=max(180, 42 * len(chart_data)), x_label="%", y_label="")
    compact = table.copy()
    compact["Eredmény"] = compact.apply(lambda r: f"{r['%']:.1f}% · {int(r['Fő'])} fő", axis=1)
    st.dataframe(compact[["Válasz", "Eredmény"]], hide_index=True, use_container_width=True)


def wine_summary(wine):
    st.subheader(wine_name(wine))
    wine_votes = fetch_votes(wine=wine)
    if wine_votes.empty:
        st.info("Ehhez a tételhez még nincs szavazat.")
        return

    st.metric("Résztvevők", wine_votes["participant"].nunique())

    st.markdown("### Illat")
    chart_for_question(wine, "illat", "intenzitas", "Illat intenzitása", ["Visszafogott", "Közepes", "Határozott"])
    chart_for_question(wine, "illat", "elsodleges_aromak", "Illat – leggyakoribb elsődleges aromák", multi=True, top_n=10)

    st.markdown("### Ízösszetétel")
    for qkey, label, options in SCALE_QUESTIONS["iz"]:
        chart_for_question(wine, "iz", qkey, label, options=options)
    chart_for_question(wine, "iz", "elsodleges_aromak", "Íz – leggyakoribb elsődleges aromák", multi=True, top_n=10)

    st.markdown("### Másodlagos aromák")
    chart_for_question(wine, "masodlagos", "aromak", "Leggyakoribb másodlagos aromák", multi=True, top_n=10)

    st.markdown("### Harmadlagos aromák")
    chart_for_question(wine, "harmadlagos", "aromak", "Leggyakoribb harmadlagos aromák", multi=True, top_n=10)


@st.fragment(run_every="3s")
def live_summary_fragment(selected_summary_wine):
    wine_summary(selected_summary_wine)


def admin_panel():
    st.title("Admin")
    admin_pw = os.getenv("ADMIN_PASSWORD", "boradmin")
    pwd = st.text_input("Admin jelszó", type="password")
    if pwd != admin_pw:
        st.info("Add meg az admin jelszót.")
        return
    st.success("Admin mód aktív")

    tasting_name = st.text_input("Kóstoló neve", value=get_setting("tasting_name", "Borok értékelése"))
    st.markdown("### Tételek neve")
    names = {}
    for i in range(1, WINE_COUNT + 1):
        names[i] = st.text_input(f"{i}. tétel", value=wine_name(i), key=f"admin_wine_{i}")
    if st.button("Nevek mentése", use_container_width=True):
        set_setting("tasting_name", tasting_name)
        for i, name in names.items():
            set_setting(f"wine_{i}_name", name.strip() or f"{i}. tétel")
        st.success("Mentve.")

    st.markdown("### Összesített adatok")
    df = fetch_votes()
    if df.empty:
        st.info("Még nincs szavazat.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("Egyedi résztvevők", df["participant"].nunique())
        c2.metric("Leadott jelölések", len(df))
        export = df.copy()
        export.insert(2, "wine_name", export["wine"].map({i: wine_name(i) for i in range(1, WINE_COUNT + 1)}))
        st.dataframe(export.sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)
        csv = export.to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV letöltése", csv, file_name="wine_votes.csv", mime="text/csv")

    st.markdown("### Adatok törlése")
    delete_wine = st.selectbox("Tétel", list(range(1, WINE_COUNT + 1)), format_func=wine_name, key="delete_wine")
    c1, c2 = st.columns(2)
    if c1.button("Kiválasztott tétel törlése", type="secondary", use_container_width=True):
        with conn() as c:
            c.execute("DELETE FROM votes WHERE wine=?", (delete_wine,))
            c.commit()
        st.warning(f"{wine_name(delete_wine)} szavazatai törölve.")
    if c2.button("MINDEN SZAVAZAT TÖRLÉSE", type="secondary", use_container_width=True):
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
        .block-container {max-width: 820px; padding-top: 1.3rem; padding-bottom: 5rem;}
        div[data-testid="stMetricValue"] {font-size: 2rem;}
        .stButton button {min-height: 3rem; font-weight: 700;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    params = st.query_params
    if params.get("admin") == "1":
        admin_panel()
        return

    tasting_name = get_setting("tasting_name", "A borok értékelése")
    st.title(tasting_name)

    wine = st.selectbox(
        "Melyik tételt értékeled?",
        list(range(1, WINE_COUNT + 1)),
        format_func=wine_name,
        key="active_wine",
    )
    st.info(f"Aktív tétel: **{wine_name(wine)}**")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Illat", "Ízösszetétel", "Másodlagos", "Harmadlagos", "Összesítés"
    ])

    with tab1:
        scale_question(wine, "illat", "intenzitas", "Illat – intenzitás", ["Visszafogott", "Közepes", "Határozott"])
        st.divider()
        primary_aroma_form(wine, "illat", "Illat – elsődleges aromák")

    with tab2:
        for qkey, label, options in SCALE_QUESTIONS["iz"]:
            scale_question(wine, "iz", qkey, label, options)
            st.divider()
        primary_aroma_form(wine, "iz", "Íz – elsődleges aromák")

    with tab3:
        multi_aroma_block(wine, "masodlagos", SECONDARY_AROMAS, "Másodlagos aromák")

    with tab4:
        multi_aroma_block(wine, "harmadlagos", TERTIARY_AROMAS, "Harmadlagos aromák")

    with tab5:
        st.subheader("A szavazatok összesítése")
        summary_wine = st.selectbox(
            list(range(1, WINE_COUNT + 1)),
            index=wine - 1,
            format_func=wine_name,
            key="summary_wine",
        )
        live_summary_fragment(summary_wine)

    st.divider()
    st.caption("Geoterroir Kutatócsoport")


if __name__ == "__main__":
    main()
