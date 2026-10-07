import os
import sqlite3
import hashlib
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_TITLE = "Borkóstoló – közönségszavazás"
DB_PATH = Path(__file__).with_name("wine_votes.db")

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

SCALE_QUESTIONS = [
    ("illat_intenzitas", "Illat – intenzitás", ["Visszafogott", "Közepes", "Határozott"]),
    ("edesseg", "Ízösszetétel – édesség", ["Száraz", "Félszáraz", "Félédes", "Édes"]),
    ("savassag", "Ízösszetétel – savasság", ["Alacsony", "Közepes", "Magas"]),
    ("tannin", "Ízösszetétel – tannin", ["Alacsony", "Közepes", "Magas"]),
    ("alkohol", "Ízösszetétel – alkohol", ["Alacsony", "Közepes", "Magas"]),
    ("testesseg", "Ízösszetétel – testesség", ["Könnyű", "Közepes", "Telt"]),
    ("iz_intenzitas", "Ízösszetétel – intenzitás", ["Könnyű", "Közepes", "Határozott"]),
    ("lecsenges", "Ízösszetétel – lecsengés", ["Rövid", "Közepes", "Hosszú"]),
]


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
                section TEXT NOT NULL,
                question TEXT NOT NULL,
                option TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vote
            ON votes(participant, section, question, option);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def get_setting(key, default=""):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key, value):
    with conn() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        c.commit()


def participant_id():
    if "participant_id" not in st.session_state:
        seed = f"{time.time_ns()}-{os.urandom(16).hex()}"
        st.session_state.participant_id = hashlib.sha256(seed.encode()).hexdigest()[:20]
    return st.session_state.participant_id


def replace_single_vote(section, question, option):
    pid = participant_id()
    with conn() as c:
        c.execute("DELETE FROM votes WHERE participant=? AND section=? AND question=?", (pid, section, question))
        c.execute(
            "INSERT INTO votes(participant, section, question, option, created_at) VALUES(?,?,?,?,?)",
            (pid, section, question, option, datetime.utcnow().isoformat()),
        )
        c.commit()


def replace_multi_votes(section, question, options):
    pid = participant_id()
    with conn() as c:
        c.execute("DELETE FROM votes WHERE participant=? AND section=? AND question=?", (pid, section, question))
        for option in options:
            c.execute(
                "INSERT INTO votes(participant, section, question, option, created_at) VALUES(?,?,?,?,?)",
                (pid, section, question, option, datetime.utcnow().isoformat()),
            )
        c.commit()


def fetch_votes(section=None, question=None):
    sql = "SELECT participant, section, question, option, created_at FROM votes WHERE 1=1"
    params = []
    if section:
        sql += " AND section=?"
        params.append(section)
    if question:
        sql += " AND question=?"
        params.append(question)
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


def result_table(section, question, options=None, multi=False):
    df = fetch_votes(section, question)
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


def render_result_bars(section, question, options=None, multi=False):
    table, voters = result_table(section, question, options, multi)
    st.caption(f"Szavazók száma: {voters} fő")
    if table.empty:
        st.info("Még nincs szavazat.")
        return
    for _, row in table.iterrows():
        st.write(f"**{row['Válasz']}** — {row['%']:.1f}% · {int(row['Fő'])} fő")
        st.progress(min(float(row["%"])/100.0, 1.0))


def primary_aroma_form(section_key, title):
    st.subheader(title)
    selected_categories = st.multiselect(
        "Mely elsődleges aromacsoportokat érzed?",
        list(PRIMARY_AROMAS.keys()),
        key=f"{section_key}_primary_categories",
    )
    detailed = []
    for cat in selected_categories:
        with st.expander(cat, expanded=True):
            vals = st.multiselect(
                "Konkrét aromák",
                PRIMARY_AROMAS[cat],
                key=f"{section_key}_{cat}",
            )
            detailed.extend([f"{cat} → {v}" for v in vals])
    if st.button("Elsődleges aromák mentése", key=f"save_{section_key}_primary", use_container_width=True):
        combined = selected_categories + detailed
        replace_multi_votes(section_key, "elsodleges_aromak", combined)
        st.success("Szavazat elmentve.")

    with st.expander("Élő eredmények", expanded=True):
        render_result_bars(section_key, "elsodleges_aromak", multi=True)


def multi_aroma_block(section_key, data, title):
    st.subheader(title)
    selected = []
    for group, options in data.items():
        vals = st.multiselect(group, options, key=f"{section_key}_{group}")
        selected.extend([f"{group} → {v}" for v in vals])
    if st.button("Aromák mentése", key=f"save_{section_key}", use_container_width=True):
        replace_multi_votes(section_key, "aromak", selected)
        st.success("Szavazat elmentve.")
    with st.expander("Élő eredmények", expanded=True):
        render_result_bars(section_key, "aromak", multi=True)


def scale_question(section, qkey, label, options):
    st.markdown(f"### {label}")
    choice = st.radio("Válassz:", options, horizontal=True, key=f"radio_{section}_{qkey}", label_visibility="collapsed")
    if st.button("Szavazok", key=f"vote_{section}_{qkey}", use_container_width=True):
        replace_single_vote(section, qkey, choice)
        st.success("Szavazat elmentve.")
    render_result_bars(section, qkey, options=options, multi=False)


def admin_panel():
    st.title("Admin")
    admin_pw = os.getenv("ADMIN_PASSWORD", "boradmin")
    pwd = st.text_input("Admin jelszó", type="password")
    if pwd != admin_pw:
        st.info("Add meg az admin jelszót.")
        return
    st.success("Admin mód aktív")
    name = st.text_input("Kóstoló / bor neve", value=get_setting("tasting_name", "Borkóstoló"))
    if st.button("Név mentése"):
        set_setting("tasting_name", name)
        st.success("Mentve.")

    st.markdown("### Összesített adatok")
    df = fetch_votes()
    if df.empty:
        st.info("Még nincs szavazat.")
    else:
        st.metric("Egyedi résztvevők", df["participant"].nunique())
        st.metric("Leadott jelölések", len(df))
        st.dataframe(df.sort_values("created_at", ascending=False), use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("CSV letöltése", csv, file_name="wine_votes.csv", mime="text/csv")

    if st.button("MINDEN SZAVAZAT TÖRLÉSE", type="secondary"):
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
        .block-container {max-width: 760px; padding-top: 1.3rem; padding-bottom: 5rem;}
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

    tasting_name = get_setting("tasting_name", "Borkóstoló")
    st.title(tasting_name)
    st.caption("Anonim, böngészős közönségszavazás")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Illat", "Ízösszetétel", "Másodlagos", "Harmadlagos", "Összesítés"
    ])

    with tab1:
        scale_question("illat", "intenzitas", "Illat – intenzitás", ["Visszafogott", "Közepes", "Határozott"])
        st.divider()
        primary_aroma_form("illat", "Illat – elsődleges aromák")

    with tab2:
        qdata = [
            ("edesseg", "Édesség", ["Száraz", "Félszáraz", "Félédes", "Édes"]),
            ("savassag", "Savasság", ["Alacsony", "Közepes", "Magas"]),
            ("tannin", "Tannin", ["Alacsony", "Közepes", "Magas"]),
            ("alkohol", "Alkohol", ["Alacsony", "Közepes", "Magas"]),
            ("testesseg", "Testesség", ["Könnyű", "Közepes", "Telt"]),
            ("intenzitas", "Intenzitás", ["Könnyű", "Közepes", "Határozott"]),
            ("lecsenges", "Lecsengés", ["Rövid", "Közepes", "Hosszú"]),
        ]
        for qkey, label, options in qdata:
            scale_question("iz", qkey, label, options)
            st.divider()
        primary_aroma_form("iz", "Íz – elsődleges aromák")

    with tab3:
        multi_aroma_block("masodlagos", SECONDARY_AROMAS, "Másodlagos aromák")

    with tab4:
        multi_aroma_block("harmadlagos", TERTIARY_AROMAS, "Harmadlagos aromák")

    with tab5:
        st.subheader("Élő összesítés")
        all_votes = fetch_votes()
        if all_votes.empty:
            st.info("Még nincs szavazat.")
        else:
            c1, c2 = st.columns(2)
            c1.metric("Résztvevők", all_votes["participant"].nunique())
            c2.metric("Jelölések", len(all_votes))
            summary = (
                all_votes.groupby(["section", "question", "option"])["participant"]
                .nunique().reset_index(name="Fő")
                .sort_values(["section", "question", "Fő"], ascending=[True, True, False])
            )
            st.dataframe(summary, use_container_width=True, hide_index=True)
            st.caption("Az eredmények frissítéséhez húzd le/frissítsd az oldalt. Streamlit Community Cloudon az oldal minden új interakciónál újraszámolódik.")

    st.divider()
    st.caption("Admin: add a URL végére ezt: ?admin=1")


if __name__ == "__main__":
    main()
