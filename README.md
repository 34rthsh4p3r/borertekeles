# GEOTerroir borértékelés

A GEOTerroir magyar nyelvű Streamlit-alkalmazás öt bortétel anonim értékelésére. A tétel és a fajtakategória kiválasztása azonnal frissíti a kérdéseket. Az **Eredmények** oldalon az adminisztrátor tételenként áttekintheti a diagramokat, az aktív és a korábbi értékeléseket, valamint letöltheti a szűrt vagy a teljes történeti adatállományt.

## Indítás helyben

Python 3.11 vagy újabb szükséges. Helyi Windows-teszteléshez Python 3.13-at használtunk. Streamlit Community Cloudban a 3.12-es vagy 3.13-as verziót válaszd.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
```

macOS vagy Linux alatt a környezet aktiválásához futtasd a `source .venv/bin/activate` parancsot, a másoláshoz pedig a `cp .streamlit/secrets.toml.example .streamlit/secrets.toml` parancsot.

Helyi kipróbáláshoz töltsd ki az `ADMIN_PASSWORD` mezőt a feladathoz megadott értékkel a saját `.streamlit/secrets.toml` fájlodban. A `[database]` szakaszban állítsd a `backend` mezőt `"sqlite"` értékre. Az alkalmazás az első adatbázis-műveletnél létrehozza a `.local-data/evaluations.sqlite3` fájlt. A helyi adatbázis hurokcímen, például `127.0.0.1` címen használható fejlesztéshez és teszteléshez. Az éles indításhoz kövesd az alábbi Supabase-lépéseket.

```bash
streamlit run app.py
```

A kérdőívet a [helyi kezdőlapon](http://localhost:8501), az adminoldalt az **Eredmények** menüben vagy a [közvetlen címen](http://localhost:8501/eredmenyek) találod. A fejléc eredeti képe az `assets/GEOTerroir_HUN.jpg`. Képcserekor ugyanide, ezzel a kis- és nagybetűérzékeny fájlnévvel kerüljön az új JPG.

## Tartós adatbázis beállítása a Supabase-ben

1. Hozz létre egy Supabase-projektet. Az **SQL Editor** felületen futtasd a [`database/schema.sql`](database/schema.sql) teljes tartalmát. Ez létrehozza a `geoterroir` sémát, az értékeléstáblát, az indexeket és a két alkalmazásszerepkört.
2. Az SQL Editorban állíts be külön, erős jelszót a két szerepkörnek. A helyőrzőket cseréld le a saját jelszavaidra, és a kitöltött parancsot tartsd a Supabase-ben.

   ```sql
   ALTER ROLE geoterroir_submit PASSWORD '<bekuldes-jelszava>';
   ALTER ROLE geoterroir_admin PASSWORD '<admin-adatbazis-jelszava>';
   ```

3. A Supabase **Connect** paneljén válaszd a **Session pooler** lehetőséget. Másold ki a pontos gépnevet és a projektazonosítót. Az alkalmazás a két külön felhasználóval, a 5432-es porton kapcsolódik. A kapcsolati URI-ban a jelszavak különleges karaktereit százalékkódolással add meg. [Supabase PostgreSQL-kapcsolatok](https://supabase.com/docs/guides/database/connecting-to-postgres)
4. Helyi PostgreSQL-próbához a `.streamlit/secrets.toml` fájlban, felhős futtatáshoz a Streamlit **Secrets** mezőben add meg az alábbi adatokat. Az `ADMIN_PASSWORD` értéke a feladatban megadott belépési jelszó. A két adatbázisjelszó a 2. lépésből származik.

   ```toml
   ADMIN_PASSWORD = ""

   [database]
   backend = "postgresql"
   submit_dsn = "postgresql://geoterroir_submit.PROJEKTREF:KODOLT_JELSZO@POOLER_HOST:5432/postgres?sslmode=require"
   admin_dsn = "postgresql://geoterroir_admin.PROJEKTREF:KODOLT_JELSZO@POOLER_HOST:5432/postgres?sslmode=require"
   ```

5. A Supabase-ben bekapcsolhatod az SSL-kényszerítést. A szerver tanúsítványának ellenőrzéséhez a kapcsolati beállításban `sslmode=verify-full` módban add meg a szolgáltató megfelelő CA-tanúsítványát. [Supabase SSL-beállítások](https://supabase.com/docs/guides/platform/ssl-enforcement)

A `geoterroir_submit` szerepkör új rekordokat szúrhat be. A `geoterroir_admin` olvashatja a rekordokat és módosíthatja a `chart_active` oszlopot. Egyik alkalmazásszerepkör sem törölhet rekordot. A Streamlit csak sikeres adminbelépés után nyit kapcsolatot az adminisztrációs szerepkörrel. Hosszú távú adatmegőrzéshez a Supabase-csomag mentési lehetőségei mellett használható rendszeres adatbázis-mentés is. [Supabase-mentések](https://supabase.com/docs/guides/platform/backups)

## Közzététel GitHubon és Streamlit Community Cloudban

1. Hozz létre egy üres GitHub-repositoryt. A projekt gyökérmappájából add hozzá az alkalmazás fájljait az alábbi módon. Az `origin` URL-t cseréld ki a saját repositoryd címére. A `git status --short` kimenetében ellenőrizd a feltöltendő fájlokat. A repositoryba a jelszó nélküli `.streamlit/secrets.toml.example` minta kerül. [Helyi projekt feltöltése GitHubra](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

   ```bash
   git init -b main
   git add .gitignore .streamlit/config.toml .streamlit/secrets.toml.example app.py requirements.txt README.md assets/GEOTerroir_HUN.jpg components database utils tests
   git status --short
   git commit -m "GEOTerroir borértékelő alkalmazás"
   git remote add origin https://github.com/FELHASZNALO/GEOTerroir.git
   git push -u origin main
   ```

2. A [Streamlit Community Cloud](https://share.streamlit.io/) felületén válaszd a **Create app** lehetőséget, majd add meg a GitHub-repositoryt, a `main` ágat és az `app.py` belépőfájlt. Az **Advanced settings** alatt válaszd ki a Python-verziót és illeszd be a kitöltött, PostgreSQL-alapú Secrets konfigurációt. [Streamlit Cloud telepítés](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Secrets kezelése](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
3. Kattints a **Deploy** gombra. A kiosztott URL-en próbálj ki egy fehér- és egy vörösboros beküldést. Az **Eredmények** oldalon ellenőrizd a két rekordot és az exportokat. Ha a próbarekordokat az éles diagramokon el szeretnéd tüntetni, archiváld őket. Ahol csak valódi szavazatok kerülhetnek a történeti exportba, külön próbaadatbázissal végezd az élesítés előtti ellenőrzést.

## Az eredmények kezelése

- A tételszűrő a statisztikákra, a diagramokra és a táblázatra is érvényes. Az átlag és az aromagyakoriság az aktív értékelésekből készül. Az **Összes tétel** nézet átlagpontszám-diagramja az öt tételt hasonlítja össze.
- Az **Értékelések** lapon szűrhetsz az aktív válaszokra, vagy megjelenítheted a teljes történetet. A táblázat időpont vagy pontszám alapján rendezhető, és száz rekordot mutat oldalanként.
- Az **Exportálás** lapon válassz a teljes adatállomány és a kiválasztott tétel között, majd kattints az **Exportfájlok előkészítése** gombra. Az alkalmazás ugyanabból az adatbázis-lekérésből készíti a CSV-t és az XLSX-et, és a fájlnevekben az előkészítés idejét tünteti fel. A két letöltés az archivált értékeléseket is tartalmazza. A CSV pontosvesszővel tagolt, UTF-8 BOM-mal. Az XLSX fagyasztott fejléccel és oszlopszűrőkkel nyílik meg. A külön dátum és `Timestamp (HH-MM-SS)` oszlop Budapest helyi idejét mutatja, nyári időszámításkor is.
- Az **Archiválás** lapon a **Szavazatok törlése** gomb megnyit egy megerősítő ablakot. A kiválasztott tételhez az ablak megnyitásáig beérkezett aktív rekordok `chart_active` mezője jóváhagyáskor `FALSE` értékre vált. Az összes tétel archiválásához egy további jelölőnégyzetet is be kell kapcsolni. A korábbi rekordok elérhetők maradnak a történeti táblázatban és az exportban. A későbbi beküldések aktívként jelennek meg.
- A kérdőív nem kér személyes azonosítót. Az alkalmazás munkamenetenként rövid szünetet hagy a mentési kísérletek között, és percenkénti terhelési korlátot alkalmaz. Az esetleg elérhető hálózati címből csak rövid életű, memóriában tárolt lenyomatot használ a korlátozáshoz. A mentés újrapróbálása az eredeti UUID-val történik.

## Projektfájlok és tesztek

| Fájl vagy mappa | Szerepe |
| --- | --- |
| `app.py` | Navigáció és Streamlit-belépőpont |
| `components/` | Kérdőív, adminfelület, diagramok és megjelenés |
| `database/` | PostgreSQL- és helyi SQLite-séma, jogosultságok és adatbázis-műveletek |
| `utils/` | Központi kérdéskészlet, szerveroldali ellenőrzés, összesítések, export és terhelési korlátok |
| `tests/` | A kritikus folyamatok automatizált tesztjei |

```bash
python -m unittest discover -s tests -v
```

Az automatizált tesztek ideiglenes adatbázist használnak. Ellenőrzik a kérdőív ágait és a hibás válaszokat, a párhuzamos mentéseket, az összesítéseket, az archiválás hatókörét, valamint az exportfájlok tartalmát és formátumát.
