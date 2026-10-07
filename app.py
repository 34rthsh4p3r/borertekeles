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

    max_pct = float(table["%"].max()) if not table.empty else 0.0

    rows = []
    for _, row in table.iterrows():
        option = html.escape(str(row["Válasz"]))
        pct = float(row["%"])
        count = int(row["Fő"])
        pct_text = fmt_pct(pct)
        winner = abs(pct - max_pct) < 0.05
        fill_class = "winner" if winner else "normal"
        value_class = "winner-text" if winner else ""
        rows.append(
            f"""
            <div class="summary-row">
                <div class="summary-option">{option}</div>
                <div class="summary-track">
                    <div class="summary-fill {fill_class}" style="width:{max(1.5, pct):.1f}%"></div>
                </div>
                <div class="summary-value {value_class}">{pct_text} ({count} fő)</div>
            </div>
            """
        )

    st.markdown(
        f"""
        <div class="summary-question">
            <div class="summary-question-title">{html.escape(label)}</div>
            {''.join(rows)}
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    render_multi_summary_line(
        wine,
        "illat",
        "elsodleges_aromak",
        "Illat – elsődleges aromák",
        top_n=5,
    )

    st.markdown("## Ízösszetétel")
    for qkey, label, options in SCALE_QUESTIONS["iz"]:
        render_single_summary_chart(wine, "iz", qkey, label, options=options)

    render_multi_summary_line(
        wine,
        "iz",
        "elsodleges_aromak",
        "Íz – elsődleges aromák",
        top_n=5,
    )

    st.markdown("## Másodlagos aromák")
    render_multi_summary_line(
        wine,
        "masodlagos",
        "aromak",
        "Leggyakoribb aromák",
        top_n=5,
    )

    st.markdown("## Harmadlagos aromák")
    render_multi_summary_line(
        wine,
        "harmadlagos",
        "aromak",
        "Leggyakoribb aromák",
        top_n=5,
    )


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
            text-transform: uppercase;
        }
        .summary-track {
            width: 100%;
            height: 18px;
            background: transparent;
            border: 1px solid #111;
            box-sizing: border-box;
            overflow: hidden;
        }
        .summary-fill {
            height: 100%;
            box-sizing: border-box;
        }
        .summary-fill.normal {
            background: #b8b8b8;
        }
        .summary-fill.winner {
            background: #00a63c;
        }
        .summary-value {
            font-size: 0.86rem;
            font-weight: 700;
            white-space: nowrap;
            text-align: left;
        }
        .summary-value.winner-text {
            color: #008c34;
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

    tasting_name = get_setting("tasting_name", "A borok értékelése")
    st.title(tasting_name)

    wine = st.selectbox(
        "Melyik tételt értékeled?",
        list(range(1, WINE_COUNT + 1)),
        format_func=wine_name,
        key="active_wine",
    )

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
        live_summary_fragment(wine)

    st.divider()
    st.caption("Geoterroir Kutatócsoport")


if __name__ == "__main__":
    main()
