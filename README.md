# GEOTerroir – bordó-fehér borkóstoló

Az egyfájlos Streamlit-alkalmazásban az illatintenzitást, az ízösszetételt, valamint az elsődleges, másodlagos és harmadlagos aromákat lehet értékelni. A fehér gombok világossárgára váltanak kiválasztáskor. Minden kattintás után automatikusan ment az alkalmazás. Az elsődleges aromák fő csoportnevei rövidek, a részletes illatjegyek csoportonként nyithatók le.

## Indítás

Python 3.11 vagy újabb szükséges. A parancsokat az `r_wines` mappában futtasd.

```bash
python -m pip install -r requirements.txt
python -m streamlit run bor_kostolo_design1.py
```

A már telepített Windows-környezetből így is elindíthatod.

```powershell
..\.venv\Scripts\python.exe -m streamlit run bor_kostolo_design1.py
```

A kóstoló a [helyi kezdőlapon](http://localhost:8501), az adminisztráció a [helyi adminoldalon](http://localhost:8501/?admin=1) érhető el. A helyi adminjelszó a Git által kihagyott `.streamlit/secrets.toml` fájlban van. Új telepítésnél a `.streamlit/secrets.toml.example` mintából hozhatod létre ezt a fájlt. Az `ADMIN_PASSWORD` környezeti változó is használható.

## Adatbázis és adminisztráció

- A `wine_votes.db` és a `GEOTerroir_HUN.jpg` a program mellett található. Ha a program mellett még nincs adatbázisfájl, az első indítás létrehozza. Meglévő `wine_votes.db` átvételéhez állítsd le a programot, készíts mentést az adatbázisról, majd helyezd a fájlt a `bor_kostolo_design1.py` mellé.
- Régi adatbázis megnyitásakor a hiányzó `wine` és `archived_at` oszlopot az alkalmazás hozzáadja. A tételszám nélküli sorok az első tételhez tartoznak. Az elsődleges aromák régi `illat` és `iz` szekcióinak azonos jelölései az összesítésben és a letöltésekben egyszer jelennek meg.
- A **Beállítások** oldalon megadható a kóstoló címe, a tételek száma 1 és 20 között, valamint a tételek neve és típusa. Az **Eredmények** lapon a kiválasztott tétel aktív jelölései három másodpercenként frissülnek.
- Az **Export és archiválás** lapon a CSV és az Excel a teljes történetet is tartalmazza. Archiváláskor a kijelölt tétel vagy külön megerősítéssel az összes tétel aktív jelölése lekerül a diagramokról. Az archivált adatok továbbra is letölthetők.
- Hosszú távú megőrzéshez a program mappájának tartós lemezen kell lennie. A Streamlit Community Cloud helyi fájltárolása nem garantál tartósságot. [Streamlit adattárolási útmutató](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)

## Tesztek

```bash
python -m unittest discover -s tests -v
```
