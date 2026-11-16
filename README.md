# GeoTerroir

A kérdőív a new_wines kérdéseit és színeit használja. A nyilvános fejlécben a GEOTerroir logó látszik.

A választott tétel típusától függően illatosságot és fehér szőlőfajtát, vagy fajtacsoportot és vörös szőlőfajtát lehet megadni. Mindkét típusnál szerepelnek az aromacsoportok, a borkészítés, a borvidék, az egyensúly és az 1–10 pontos értékelés. A teljes kérdőív az **Értékelés beküldése** gombbal kerül az adatbázisba.

## Indítás

Python 3.11 vagy újabb szükséges. Az `r_wines` mappában futtasd ezeket a parancsokat.

```bash
python -m pip install -r requirements.txt
python -m streamlit run bor_kostolo_design1.py
```

A már telepített Windows-környezetből a `..\.venv\Scripts\python.exe -m streamlit run bor_kostolo_design1.py` paranccsal is indíthatod.

A kérdőív a [helyi kezdőlapon](http://localhost:8501), az adminisztráció a [helyi adminoldalon](http://localhost:8501/?admin=1) érhető el. A helyi jelszó a Git által kihagyott `.streamlit/secrets.toml` fájlban van. Új telepítésnél a `.streamlit/secrets.toml.example` alapján készíts saját fájlt, vagy állítsd be az `ADMIN_PASSWORD` környezeti változót.

## Adatbázis és adminisztráció

- A logó és a `wine_votes.db` adatbázis a programfájl mellett található. Ha az adatbázis még hiányzik, az alkalmazás létrehozza. Meglévő adatbázis átvételéhez állítsd le az alkalmazást, készíts mentést, majd helyezd a fájlt a program mellé.
- Az új értékelések az `evaluations` táblába kerülnek. A korábbi kérdőív jelölései a `votes` táblában maradnak, és az **Exportálás** lapon külön CSV-ként tölthetők le.
- A **Beállítások** lapon öt tétel az alapértelmezés. A tételek száma, neve, valamint fehér- vagy vörösbor típusa módosítható.
- A **Diagramok** lap három másodpercenként frissül. Az **Archiválás** lapon jóváhagyás után a választott értékelések lekerülnek az aktív diagramokról. A történeti adatok továbbra is letölthetők CSV és Excel formátumban.
- Hosszú távú megőrzéshez az SQLite-fájlt tartós lemezen kell tárolni. A Streamlit Community Cloud helyi fájltárolása ezt nem garantálja. [Streamlit adattárolási útmutató](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)

## Tesztelés

```bash
python -m unittest discover -s tests -v
```
