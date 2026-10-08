"""GeoTerroir közönségszavazás. Indítás: streamlit run app.py"""
from __future__ import annotations

import hashlib
import hmac
import html
import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("VOTES_DB_PATH", str(BASE_DIR / "votes.sqlite3")))
DEFAULT_TITLE = "Magyar borvidékek geológiája és kultúrája"
WINE_TYPES = ("Fehér", "Rozé", "Vörös")
WINE_COLORS = {
    "Fehér": "rgb(244, 241, 186)",
    "Rozé": "rgb(245, 124, 131)",
    "Vörös": "rgb(187, 34, 40)",
}
PRIMARY = {
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
SECONDARY = {
    "Élesztő": ["keksz", "kenyér", "pirítós", "kenyértészta", "sajt", "joghurt"],
    "Malolaktikus erjedés": ["vaj", "tejszín", "sajt", "joghurt"],
    "Tölgyfahordós jegyek": ["vanília", "szegfűszeg", "szerecsendió", "kókusz", "karamella",
                            "pirítós", "égett fa", "füst", "csokoládé", "kávé", "gyanta", "cédrus"],
}
TERTIARY = {
    "Oxidáció": ["mandula", "mogyoró", "dió", "csokoládé", "kávé", "karamell"],
    "Vörösbor": ["szárított gyümölcs", "bőr", "föld", "gomba", "erdei talaj", "hús",
                "dohány", "nedves levél", "karamell"],
    "Fehérbor": ["szárított gyümölcs", "narancslekvár", "petrol (benzin)", "fahéj",
                "gyömbér", "szerecsendió", "mogyoró", "méz", "karamell"],
}
SCENT_SCALES = {"intenzitas": ("Illat intenzitása", ["Visszafogott", "Közepes", "Határozott"])}
TASTE_SCALES = {
    "edesseg": ("Édesség", ["Száraz", "Félszáraz", "Félédes", "Édes"]),
    "savassag": ("Savasság", ["Alacsony", "Közepes", "Magas"]),
    "tannin": ("Tannin", ["Alacsony", "Közepes", "Magas"]),
    "alkohol": ("Alkohol", ["Alacsony", "Közepes", "Magas"]),
    "testesseg": ("Testesség", ["Könnyű", "Közepes", "Telt"]),
    "intenzitas": ("Intenzitás", ["Könnyű", "Közepes", "Határozott"]),
    "lecsenges": ("Lecsengés", ["Rövid", "Közepes", "Hosszú"]),
}


@contextmanager
def conn():
    """Minden művelet saját kapcsolatot használ; commit/rollback és lezárás garantált."""
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with conn() as database:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.execute("""CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant TEXT NOT NULL, wine INTEGER NOT NULL CHECK(wine BETWEEN 1 AND 50),
            section TEXT NOT NULL, question TEXT NOT NULL, option TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        database.execute("CREATE UNIQUE INDEX IF NOT EXISTS vote_unique ON votes(participant,wine,section,question,option)")
        database.execute("CREATE INDEX IF NOT EXISTS vote_question ON votes(wine,section,question)")
        defaults = {"title": DEFAULT_TITLE, "wine_count": "5", "revision": "0", "public_url": ""}
        for wine in range(1, 51):
            defaults[f"wine_{wine}_name"] = f"{wine}. tétel"
            defaults[f"wine_{wine}_type"] = "Fehér"
        database.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", defaults.items())


def all_settings():
    with conn() as database:
        return dict(database.execute("SELECT key,value FROM settings").fetchall())


def get_setting(key, default=""):
    with conn() as database:
        row = database.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with conn() as database:
        database.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def wine_count(settings=None):
    return int((settings or all_settings()).get("wine_count", "5"))


def wine_name(wine, settings=None):
    return (settings or all_settings()).get(f"wine_{wine}_name", f"{wine}. tétel")


def wine_type(wine, settings=None):
    return (settings or all_settings()).get(f"wine_{wine}_type", "Fehér")


def wine_color(wine, settings=None):
    return WINE_COLORS[wine_type(wine, settings)]


def participant_id():
    if "participant_id" not in st.session_state:
        st.session_state.participant_id = hashlib.sha256(os.urandom(32)).hexdigest()
    return st.session_state.participant_id


def replace_multi_votes(participant, wine, section, question, options, expected_revision=None):
    """Egy kérdés teljes aktuális halmazának atomi cseréje (üres halmaz = törlés)."""
    with conn() as database:
        database.execute("BEGIN IMMEDIATE")
        settings = dict(database.execute("SELECT key,value FROM settings").fetchall())
        # Régi böngészőesemény nem állíthatja vissza az admin által törölt adatokat.
        if expected_revision is not None and settings["revision"] != expected_revision:
            raise ValueError("A kóstoló beállításai megváltoztak. A felület frissült; válassz újra.")
        if wine < 1 or wine > wine_count(settings):
            raise ValueError("Ez a tétel már nem aktív. Válassz másik tételt.")
        if section == "iz" and question == "tannin" and wine_type(wine, settings) == "Fehér":
            return
        database.execute("DELETE FROM votes WHERE participant=? AND wine=? AND section=? AND question=?",
                         (participant, wine, section, question))
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        database.executemany("INSERT INTO votes(participant,wine,section,question,option,created_at) VALUES (?,?,?,?,?,?)",
                             [(participant, wine, section, question, option, now) for option in dict.fromkeys(options)])


def replace_single_vote(participant, wine, section, question, option, expected_revision=None):
    replace_multi_votes(participant, wine, section, question, [] if option is None else [option], expected_revision)


def fetch_votes(wine=None):
    with conn() as database:
        if wine is None:
            return pd.read_sql_query("SELECT * FROM votes ORDER BY id", database)
        return pd.read_sql_query("SELECT * FROM votes WHERE wine=? ORDER BY id", database, params=(wine,))


def result_table(votes, section, question, options=None, single_choice=True):
    """Egy fő = egy különböző résztvevő; multi esetén nincs százalékos oszlop."""
    subset = votes[(votes["section"] == section) & (votes["question"] == question)]
    counts = subset.groupby("option")["participant"].nunique()
    labels = list(options) if options is not None else sorted(counts.index, key=lambda label: (-counts[label], label))
    result = pd.DataFrame({"válasz": labels, "fő": [int(counts.get(label, 0)) for label in labels]})
    if single_choice:
        total = int(result["fő"].sum())
        result["százalék"] = result["fő"] * 100 / total if total else 0.0
    else:
        result = result[result["fő"] > 0].reset_index(drop=True)
    return result


def widget_key(kind, wine, section, question, suffix=""):
    return f"{kind}_w{wine}_{section}_{question}_{suffix}"


def own_options(wine, section, question):
    with conn() as database:
        return [row[0] for row in database.execute(
            "SELECT option FROM votes WHERE participant=? AND wine=? AND section=? AND question=?",
            (participant_id(), wine, section, question))]


def save_widget_vote(wine, section, question, options, single=False):
    try:
        function = replace_single_vote if single else replace_multi_votes
        function(participant_id(), wine, section, question, options, st.session_state.get("data_revision"))
        st.session_state["save_notice"] = "A választásod mentve."
    except (sqlite3.Error, ValueError) as error:
        # Sikertelen mentéskor a következő render az adatbázisból állítja helyre a widgeteket.
        st.session_state["data_revision"] = None
        st.session_state["save_error"] = str(error)


def single_callback(wine, section, question, key):
    save_widget_vote(wine, section, question, st.session_state[key], single=True)


def scale_question(wine, section, question, label, options):
    key = widget_key("radio", wine, section, question)
    if key not in st.session_state:
        saved = own_options(wine, section, question)
        st.session_state[key] = next((option for option in saved if option in options), None)
    st.radio(label, options, index=None, horizontal=True, key=key,
             on_change=single_callback, args=(wine, section, question, key))


def primary_callback(wine, section):
    question = "elsodleges_aromak"
    main_key = widget_key("primary", wine, section, question)
    categories = st.session_state.get(main_key, [])
    values = list(categories)
    for category in PRIMARY:
        detail_key = widget_key("detail", wine, section, question, category)
        if category not in categories:
            st.session_state.pop(detail_key, None)
        else:
            values.extend(f"{category} → {option}" for option in st.session_state.get(detail_key, []))
    save_widget_vote(wine, section, question, values)


def primary_aroma_form(wine, section):
    st.subheader("Elsődleges aromák")
    st.caption("Válassz kategóriákat, majd igény szerint konkrét aromákat.")
    question = "elsodleges_aromak"
    saved = own_options(wine, section, question)
    main_key = widget_key("primary", wine, section, question)
    if main_key not in st.session_state:
        st.session_state[main_key] = [category for category in PRIMARY if category in saved]
    categories = st.multiselect("Fő aromakategóriák", list(PRIMARY), key=main_key,
                               on_change=primary_callback, args=(wine, section))
    for category in categories:
        with st.expander(category, expanded=True):
            key = widget_key("detail", wine, section, question, category)
            if key not in st.session_state:
                st.session_state[key] = [option for option in PRIMARY[category] if f"{category} → {option}" in saved]
            st.multiselect(f"{category} – részletes aromák", PRIMARY[category], key=key,
                           on_change=primary_callback, args=(wine, section))


def multi_callback(wine, section, question, groups):
    values = []
    for group in groups:
        key = widget_key("multi", wine, section, question, group)
        values.extend(f"{group} → {option}" for option in st.session_state.get(key, []))
    save_widget_vote(wine, section, question, values)


def multi_aroma_block(wine, question, title, groups):
    st.subheader(title)
    saved = own_options(wine, "iz", question)
    for group, options in groups.items():
        key = widget_key("multi", wine, "iz", question, group)
        if key not in st.session_state:
            st.session_state[key] = [option for option in options if f"{group} → {option}" in saved]
    for group, options in groups.items():
        st.multiselect(group, options, key=widget_key("multi", wine, "iz", question, group),
                       on_change=multi_callback, args=(wine, "iz", question, groups))


CSS = """<style>
.block-container{max-width:900px;padding-top:2rem;padding-bottom:3rem}
.gt-header{display:flex;gap:20px;align-items:center;margin-bottom:1.3rem}
.gt-header h1{font-size:clamp(1.6rem,4vw,2.5rem);line-height:1.18;margin:0;overflow-wrap:anywhere}
.gt-brand{font-size:.9rem;color:inherit;opacity:.75;letter-spacing:.05em;margin:8px 0}
.result-chart{display:grid;gap:12px;margin:12px 0 24px}
.result-row{display:grid;grid-template-columns:minmax(110px,180px) minmax(100px,1fr) 110px;align-items:center;gap:12px}
.result-label{font-size:.95rem;overflow-wrap:anywhere;line-height:1.3}
.result-track{height:22px;border:1px solid black;background:#f1f1f1;overflow:hidden;border-radius:3px}
.result-fill{height:100%;min-width:0}
.result-value{font-variant-numeric:tabular-nums;text-align:right;font-size:.9rem;white-space:nowrap}
div[data-testid="stRadio"] [role="radiogroup"]{flex-wrap:wrap;gap:4px 16px}
div[data-testid="stRadio"] label{min-height:44px;align-items:center}
div[data-baseweb="select"]>div{min-height:44px}
.stButton button,.stDownloadButton button{min-height:44px}
@media(max-width:600px){
 .block-container{padding:1rem .8rem 2rem}
 .gt-header{gap:12px;flex-wrap:wrap}
 .result-row{grid-template-columns:82px minmax(60px,1fr) 82px;gap:7px}
 .result-value,.result-label{font-size:.8rem}
 .result-track{height:20px}
 button[data-baseweb="tab"]{padding-left:8px;padding-right:8px}
}
</style>"""


def chart_row(label, width, color, value):
    # Nincs minimumszélesség; nulla szavazat pontosan 0%-os kitöltést kap.
    return (f'<div class="result-row"><div class="result-label">{html.escape(str(label))}</div>'
            f'<div class="result-track" aria-hidden="true"><div class="result-fill" '
            f'style="width:{width:.6f}%;background:{color}"></div></div>'
            f'<div class="result-value">{html.escape(value)}</div></div>')


def render_single_summary_chart(table, color):
    max_pct = float(table["százalék"].max()) if not table.empty else 0.0
    rows = []
    for _, row in table.iterrows():
        pct = float(row["százalék"])
        fill_color = color if abs(pct - max_pct) < 0.05 else "rgb(184, 184, 184)"
        # Egy tizedesre kerekítve a kis, de nem nulla arányok is láthatók.
        value = f'{pct:.1f}% ({int(row["fő"])} fő)'.replace(".0%", "%").replace(".", ",")
        rows.append(chart_row(row["válasz"], pct, fill_color, value))
    st.markdown('<div class="result-chart">' + "".join(rows) + "</div>", unsafe_allow_html=True)


def render_multi_summary_chart(table, color):
    if table.empty:
        st.caption("Még nincs aromaszavazat.")
        return
    maximum = int(table["fő"].max())
    rows = [chart_row(row["válasz"], int(row["fő"]) * 100 / maximum, color, f'{int(row["fő"])} fő')
            for _, row in table.iterrows()]
    st.markdown('<div class="result-chart">' + "".join(rows) + "</div>", unsafe_allow_html=True)


def wine_summary(wine, settings=None):
    settings = settings or all_settings()
    votes = fetch_votes(wine)
    color = wine_color(wine, settings)
    st.header(wine_name(wine, settings))
    st.caption({"Fehér": "Fehérbor", "Rozé": "Rozébor", "Vörös": "Vörösbor"}[wine_type(wine, settings)])
    st.write(f'**{votes["participant"].nunique()} résztvevő** értékelte ezt a tételt.')
    st.caption("Élő összesítés · frissítés 3 másodpercenként · a skálákon a legtöbb szavazatot kapott válaszok színesek.")
    st.subheader("Illat")
    for question, (label, options) in SCENT_SCALES.items():
        st.write(f"**{label}**")
        render_single_summary_chart(result_table(votes, "illat", question, options), color)
    st.subheader("Ízösszetétel")
    for question, (label, options) in TASTE_SCALES.items():
        if question == "tannin" and wine_type(wine, settings) == "Fehér":
            continue
        st.write(f"**{label}**")
        render_single_summary_chart(result_table(votes, "iz", question, options), color)
    st.caption("Az aromák sávhossza a legtöbb szavazatot kapott aromához viszonyított darabszám; nem százalék.")
    for section, question, title, options in [
        ("illat", "elsodleges_aromak", "Illat – elsődleges aromák", list(PRIMARY)),
        ("iz", "elsodleges_aromak", "Íz – elsődleges aromák", list(PRIMARY)),
        ("iz", "masodlagos_aromak", "Másodlagos aromák", None),
        ("iz", "harmadlagos_aromak", "Harmadlagos aromák", None),
    ]:
        st.subheader(title)
        render_multi_summary_chart(result_table(votes, section, question, options, single_choice=False), color)


def synchronize_session(settings):
    revision = settings["revision"]
    if st.session_state.get("data_revision") != revision:
        for key in list(st.session_state):
            if key.startswith(("radio_w", "primary_w", "detail_w", "multi_w")):
                del st.session_state[key]
        st.session_state["data_revision"] = revision
        return True
    return False


@st.fragment(run_every="3s")
def live_summary_fragment(wine):
    settings = all_settings()
    if settings["revision"] != st.session_state.get("data_revision"):
        st.rerun()  # Admin-változáskor az egész szavazófelületet is szinkronizáljuk.
    wine_summary(wine, settings)


def config_value(key, default=""):
    if os.environ.get(key):
        return os.environ[key]
    try:
        return str(st.secrets.get(key, default))
    except FileNotFoundError:
        return default


def public_vote_url(value):
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Teljes http:// vagy https:// címet adj meg, felhasználónév és jelszó nélkül.")
    query = urlencode([(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key != "admin"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))


def qr_image(url):
    buffer = io.BytesIO()
    qrcode.make(url).save(buffer, format="PNG")
    return buffer.getvalue()


def show_qr(url, download=False):
    image = qr_image(url)
    st.image(image, width=220, caption="Olvasd be a telefonod kamerájával!")
    st.link_button("Szavazófelület megnyitása", url)
    if download:
        st.download_button("QR-kód letöltése", image, "borkostolo_qr.png", "image/png")


def save_settings(values):
    with conn() as database:
        database.execute("BEGIN IMMEDIATE")
        database.executemany("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             [(key, str(value)) for key, value in values.items()])
        database.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def delete_votes(wine=None):
    with conn() as database:
        database.execute("BEGIN IMMEDIATE")
        if wine is None:
            database.execute("DELETE FROM votes")
        else:
            database.execute("DELETE FROM votes WHERE wine=?", (wine,))
        database.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")


def export_votes():
    with conn() as database:
        return pd.read_sql_query("""SELECT v.participant,v.wine,
            COALESCE(n.value,CAST(v.wine AS TEXT)) AS wine_name,
            COALESCE(t.value,'Fehér') AS wine_type,
            v.section,v.question,v.option,v.created_at FROM votes v
            LEFT JOIN settings n ON n.key='wine_'||v.wine||'_name'
            LEFT JOIN settings t ON t.key='wine_'||v.wine||'_type' ORDER BY v.id""", database)


def admin_panel():
    st.header("Adminfelület")
    password = config_value("ADMIN_PASSWORD", "boradmin26")
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(st.session_state.get("admin_token", ""), digest):
        with st.form("admin_login"):
            candidate = st.text_input("Admin jelszó", type="password")
            submitted = st.form_submit_button("Belépés")
        if submitted:
            if hmac.compare_digest(candidate.encode("utf-8"), password.encode("utf-8")):
                st.session_state["admin_token"] = digest
                st.rerun()
            st.error("Hibás jelszó.")
        return
    if st.button("Kijelentkezés"):
        st.session_state.pop("admin_token", None)
        st.rerun()
    if password == "boradmin26":
        st.warning("Fejlesztési jelszó aktív. Nyilvános használat előtt állítsd be az ADMIN_PASSWORD értékét.")
    if notice := st.session_state.pop("admin_notice", None):
        st.success(notice)
    settings = all_settings()
    count = int(st.number_input("Hány tétel legyen?", min_value=1, max_value=50,
                                value=wine_count(settings), step=1, key="admin_wine_count"))
    st.caption("A darabszám és a többi módosítás a Beállítások mentése gombbal lép életbe. A kivett tételek adatai megmaradnak.")
    with st.form("admin_settings"):
        title = st.text_input("Kóstoló címe", value=settings["title"], max_chars=200)
        public_url = st.text_input("Nyilvános szavazó URL (QR-kódhoz)", value=settings["public_url"],
                                   placeholder="https://valami.streamlit.app/")
        values = {"wine_count": count}
        for wine in range(1, count + 1):
            st.markdown(f"**{wine}. tétel**")
            values[f"wine_{wine}_name"] = st.text_input("Tétel neve", value=wine_name(wine, settings),
                                                       key=f"admin_name_{wine}", max_chars=160)
            values[f"wine_{wine}_type"] = st.selectbox("Bortípus", WINE_TYPES,
                                                      index=WINE_TYPES.index(wine_type(wine, settings)), key=f"admin_type_{wine}")
        if st.form_submit_button("Beállítások mentése"):
            try:
                values["title"] = title.strip() or DEFAULT_TITLE
                values["public_url"] = public_vote_url(public_url) if public_url.strip() else ""
                for wine in range(1, count + 1):
                    values[f"wine_{wine}_name"] = values[f"wine_{wine}_name"].strip() or f"{wine}. tétel"
                save_settings(values)
                st.session_state["admin_notice"] = "A beállítások mentve."
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    st.subheader("Megosztás")
    url = config_value("PUBLIC_URL") or settings["public_url"]
    if url:
        try:
            show_qr(public_vote_url(url), download=True)
        except ValueError as error:
            st.error(str(error))
    else:
        st.info("A QR-kódhoz add meg és mentsd a telefonokról elérhető nyilvános URL-t.")
    st.subheader("Szavazatok exportálása")
    st.download_button("Szavazatok letöltése CSV-ben", export_votes().to_csv(index=False).encode("utf-8-sig"),
                       "borkostolo_szavazatok.csv", "text/csv")
    st.subheader("Szavazatok törlése")
    # Archivált tételeket is lehet külön törölni.
    existing_wines = fetch_votes()["wine"].unique().tolist()
    wine_ids = sorted(set(range(1, wine_count(settings) + 1)) | set(existing_wines))
    selected = st.selectbox("Törlendő tétel", wine_ids, format_func=lambda wine: f"{wine}. – {wine_name(wine, settings)}",
                            key="delete_wine")
    with st.form("delete_one"):
        confirmed = st.checkbox("Megerősítem a kiválasztott tétel szavazatainak törlését")
        if st.form_submit_button("Tétel szavazatainak törlése"):
            if confirmed:
                delete_votes(selected)
                st.session_state["admin_notice"] = "A kiválasztott tétel szavazatai törölve."
                st.rerun()
            st.error("A törléshez jelöld be a megerősítést.")
    with st.form("delete_all"):
        confirmed = st.checkbox("Megerősítem minden tétel összes szavazatának törlését")
        if st.form_submit_button("Minden szavazat törlése"):
            if confirmed:
                delete_votes()
                st.session_state["admin_notice"] = "Minden szavazat törölve."
                st.rerun()
            st.error("A törléshez jelöld be a megerősítést.")


def render_header(title):
    logo = BASE_DIR / "GEOTerroir_HUN.jpg"
    logo_html = ""
    if logo.exists():
        import base64
        encoded = base64.b64encode(logo.read_bytes()).decode("ascii")
        logo_html = f'<img src="data:image/jpeg;base64,{encoded}" alt="GeoTerroir Kutatócsoport logója" style="width:110px;max-width:28%;height:auto">'
    st.markdown('<div class="gt-header">' + logo_html + '<div><p class="gt-brand">GeoTerroir Kutatócsoport</p>'
                + f'<h1>{html.escape(title)}</h1></div></div>', unsafe_allow_html=True)


def main():
    st.set_page_config(page_title=DEFAULT_TITLE, page_icon="🍷", layout="centered")
    init_db()
    st.markdown(CSS, unsafe_allow_html=True)
    settings = all_settings()
    render_header(settings["title"])
    if st.query_params.get("admin") == "1":
        admin_panel()
        return
    participant_id()
    synchronize_session(settings)
    count = wine_count(settings)
    if st.session_state.get("active_wine", 1) > count:
        st.session_state["active_wine"] = 1
    wine = st.selectbox("Melyik tételt értékeled?", list(range(1, count + 1)),
                        format_func=lambda value: f"{value}. – {wine_name(value, settings)}", key="active_wine")
    st.caption(f"{wine_type(wine, settings)} · Minden választás automatikusan mentődik. Bármikor módosíthatod.")
    if error := st.session_state.pop("save_error", None):
        st.error(f"A választás nem mentődött: {error}")
    elif notice := st.session_state.pop("save_notice", None):
        st.success(notice)
    scent_tab, taste_tab, summary_tab = st.tabs(["Illat", "Ízösszetétel", "Összesítés"])
    with scent_tab:
        for question, (label, options) in SCENT_SCALES.items():
            scale_question(wine, "illat", question, label, options)
        primary_aroma_form(wine, "illat")
    with taste_tab:
        for question, (label, options) in TASTE_SCALES.items():
            if question == "tannin" and wine_type(wine, settings) == "Fehér":
                continue
            scale_question(wine, "iz", question, label, options)
        primary_aroma_form(wine, "iz")
        multi_aroma_block(wine, "masodlagos_aromak", "Másodlagos aromák", SECONDARY)
        multi_aroma_block(wine, "harmadlagos_aromak", "Harmadlagos aromák", TERTIARY)
    with summary_tab:
        live_summary_fragment(wine)
    url = config_value("PUBLIC_URL") or settings["public_url"]
    if url:
        with st.expander("Megosztás QR-kóddal"):
            try:
                show_qr(public_vote_url(url))
            except ValueError:
                st.info("A megosztási címet az admin tudja javítani.")
    st.caption("Anonim böngészőmunkamenet. Az oldal újratöltése vagy új böngészőablak új résztvevőazonosítót adhat.")


if __name__ == "__main__":
    main()
