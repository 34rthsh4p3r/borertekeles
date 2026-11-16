# GEOTerroir borértékelés

A `new_wines` változat öt bortétel anonim értékelésére szolgál. Az aromaválasztóban a rövid aromanevek jelennek meg. Az illatjegyek példái az **Aromacsoportok részletesen** résznél olvashatók. Az **Eredmények** oldal jelszóval védett, és tételenkénti diagramokat, történeti táblázatot, CSV- és Excel-exportot kínál.

## Indítás helyben

Python 3.11 vagy újabb szükséges. A parancsokat a `new_wines` mappában futtasd.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

macOS vagy Linux alatt a környezet aktiválásához futtasd a `source .venv/bin/activate` parancsot. Ha a projekt szülőmappájában már telepítetted a függőségeket a meglévő Windows-környezetbe, a `new_wines` mappából a `..\.venv\Scripts\python.exe -m streamlit run app.py` paranccsal is indíthatod.

Az első érvényes mentés vagy az első adminisztrátori adatlekérés létrehozza a `.local-data/wine_votes_db.sqlite3` SQLite-adatbázist. A helyi `.streamlit/secrets.toml` tartalmazza az adminjelszót és a `[database]` szakaszban a `backend = "sqlite"` beállítást. Ha GitHubról klónozod az alkalmazást, készíts erről a fájlról saját példányt a [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) alapján, és írd be a megadott adminjelszót az `ADMIN_PASSWORD` mezőbe.

A kérdőív a [helyi kezdőlapon](http://localhost:8501), az adminisztráció az **Eredmények** menüben érhető el. A fejléc eredeti képe az `assets/GEOTerroir_HUN.jpg` fájlban van.

## Tartós mentés a Streamlit Community Cloudban

A felhős alkalmazás egy elérhető PostgreSQL-szerveren lévő `wine_votes_db` adatbázisba ment. A Streamlit Community Cloud helyi fájljainak megőrzése nem garantált. [Streamlit adattárolási útmutató](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)

1. A PostgreSQL-szerveren hozd létre a `wine_votes_db` adatbázist. Csatlakozz ehhez az adatbázishoz, és futtasd a [database/schema.sql](database/schema.sql) fájlt adatbázis-adminisztrátorként.
2. Állíts be két külön szerepkörjelszót a PostgreSQL-ben. A helyőrzőket cseréld a saját értékeidre.

   ```sql
   ALTER ROLE geoterroir_submit PASSWORD 'BEKULDESI_JELSZO';
   ALTER ROLE geoterroir_admin PASSWORD 'ADATBAZIS_ADMIN_JELSZO';
   ```

3. Töltsd fel a `new_wines` projektfájljait a GitHub-repository gyökerébe. A `.gitignore` kihagyja a helyi jelszófájlt és az SQLite-adatbázist. A Streamlit Community Cloud telepítőjében add meg a repositoryt, az ágat és az `app.py` belépőfájlt. Válassz Python 3.12 vagy 3.13 környezetet. [Streamlit Cloud telepítési útmutató](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
4. A Streamlit **Advanced settings → Secrets** vagy **App settings → Secrets** mezőjében add meg az adminjelszót, valamint a két külön adatbázis-kapcsolatot. A példában cseréld ki a gépnevet, a portot és a jelszavakat a szolgáltatód adataira. A jelszavak különleges karaktereit a kapcsolati URI-ban százalékkódolással add meg. [Streamlit Secrets útmutató](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

   ```toml
   ADMIN_PASSWORD = ""

   [database]
   backend = "postgresql"
   submit_dsn = "postgresql://geoterroir_submit:KODOLT_JELSZO@POSTGRES_HOST:5432/wine_votes_db?sslmode=require"
   admin_dsn = "postgresql://geoterroir_admin:KODOLT_JELSZO@POSTGRES_HOST:5432/wine_votes_db?sslmode=require"
   ```

5. A telepítés után küldj be egy próbaértékelést, és ellenőrizd az **Eredmények** oldalon. A `geoterroir_submit` szerepkör rekordokat szúrhat be, a `geoterroir_admin` olvashatja az adatokat és módosíthatja a diagramok aktív jelzőjét.

## Eredmények és tesztelés

- A tételszűrő a statisztikákra, a diagramokra és a táblázatra is érvényes.
- Az **Exportálás** lapon készítsd elő a teljes vagy a tételenként szűrt adatállományt, majd töltsd le CSV vagy Excel formátumban. Mindkettő tartalmazza az archivált rekordokat és a budapesti helyi időt.
- Az **Archiválás** lapon a **Szavazatok törlése** gomb jóváhagyás után a diagramokról veszi le a szavazatokat. A történeti táblázatban és az exportban továbbra is szerepelnek.
- Az automatizált tesztek futtatása `python -m unittest discover -s tests -v`.
