from dataclasses import dataclass
from zoneinfo import ZoneInfo


BUDAPEST = ZoneInfo("Europe/Budapest")
WINE_TYPES = ("Fehérbor", "Vörösbor")
MAX_LOTS = 20


@dataclass(frozen=True)
class WineLot:
    name: str
    wine_type: str


DEFAULT_LOTS = {
    number: WineLot(f"{number}. tétel", "Fehérbor" if number <= 3 else "Vörösbor")
    for number in range(1, 6)
}

LOT_QUESTION = "Válaszd ki az értékelni kívánt tételt!"
AROMA_QUESTION = "Jellemző aromacsoportok"
TECHNIQUE_QUESTION = "Reduktív vagy oxidatív volt a borkészítés?"
FRAGRANCE_QUESTION = "Illatos vagy nem illatos?"
GROUP_QUESTION = "Világfajta vagy Kárpát-medencei?"
REGION_QUESTION = "Melyik borvidékről származhat?"
BALANCE_QUESTION = "Egyensúlyos vagy nem egyensúlyos?"
SCORE_QUESTION = "Értékelje a bort az ízlése szerint:"

AROMAS = {
    "florális": "akác, kamilla, bodza, rózsa, ibolya, virág",
    "zöld gyümölcs": "zöldalma, egres, körte, szőlő",
    "citrusféle": "citrom, lime, narancs, grapefruit",
    "csonthéjas": "őszibarack, sárgabarack, nektarin",
    "trópusi": "banán, licsi, mangó, dinnye, ananász, maracuja",
    "piros bogyós": "ribizli, vörösáfonya, málna, eper, meggy, cseresznye",
    "fekete bogyós": "feketeribizli, szeder, kékáfonya, kései meggy, szilva",
    "fűszeres": "fűszer, fekete bors, fehér bors, édesgyökér",
    "füves": "zöldpaprika, fű, paradicsomlevél, spárga, borsó",
    "gyógynövényes": "eukaliptusz, menta, édeskömény, kapor",
    "hordós": "pirítós, vaj, vanília, karamella, fa, füst stb.",
}
TECHNIQUES = ("Reduktív", "Oxidatív")
BALANCES = ("Egyensúlyos", "Nem egyensúlyos")

WHITE_VARIETIES = {
    "Illatos": (
        "Melyik illatos fajta lehet?",
        ("Irsai Olivér", "Cserszegi Fűszeres", "Sárgamuskotály", "Tramini", "Sauvignon Blanc"),
    ),
    "Nem illatos": (
        "Melyik nem illatos fajta lehet?",
        ("Furmint", "Hárslevelű", "Olaszrizling", "Rajnai Rizling", "Chardonnay"),
    ),
}
RED_VARIETIES = {
    "Világfajta": (
        "Melyik világfajta lehet?",
        ("Cabernet Sauvignon", "Cabernet Franc", "Merlot", "Pinot Noir", "Syrah / Shiraz"),
    ),
    "Kárpát-medencei": (
        "Melyik Kárpát-medencei fajta lehet?",
        ("Kékfrankos", "Kadarka", "Portugieser", "Feketeleányka", "Bikavér"),
    ),
}
REGIONS = (
    "Soproni borvidék",
    "Somlói borvidék",
    "Zalai borvidék",
    "Balaton-felvidéki borvidék",
    "Badacsonyi borvidék",
    "Balatonfüred–Csopaki borvidék",
    "Balatonboglári borvidék",
    "Pannonhalmi borvidék",
    "Móri borvidék",
    "Etyek–Budai borvidék",
    "Neszmélyi borvidék",
    "Tolnai borvidék",
    "Szekszárdi borvidék",
    "Pécsi borvidék",
    "Villányi borvidék",
    "Hajós–Bajai borvidék",
    "Kunsági borvidék",
    "Csongrádi borvidék",
    "Mátrai borvidék",
    "Egri borvidék",
    "Bükki borvidék",
    "Tokaji borvidék",
)
SCORES = {
    1: ("Ihatatlan", "súlyosan és menthetetlenül hibás tétel"),
    2: ("Súlyosan hibás", "dugós, oxidált vagy technológiailag elrontott bor"),
    3: ("Élvezhetetlen", "ihatatlanul savas, keserű vagy maróan alkoholos"),
    4: ("Átlag alatti", "unalmas, teljesen jellegtelen, „vékony” bor"),
    5: ("Korrekt alapbor", "tiszta, hibátlan, de teljesen egyszerű tétel"),
    6: ("Jó", "jó ivású, kellemes mindennapi bor, hozza a fajtajellegeket"),
    7: ("Nagyon jó", "komolyabb szerkezetű bor, szép egyensúllyal"),
    8: ("Kiváló", "kiemelkedő minőség, remek egyensúly és egyedi karakter"),
    9: ("Kivételes / Csúcsbor", "izgalmas és emlékezetes bor, tökéletes harmónia"),
    10: ("Tökéletes", "hibátlan, felejthetetlen élményt nyújtó ikonikus bor"),
}


def lot_label(lot: int | None, lots: dict[int, WineLot]) -> str:
    if lot is None:
        return "Összes tétel"
    entry = lots[lot]
    return f"{entry.name} ({entry.wine_type.lower()})"


def variety_branch(wine_type: str):
    if wine_type == "Fehérbor":
        return "fragrance", FRAGRANCE_QUESTION, WHITE_VARIETIES
    return "variety_group", GROUP_QUESTION, RED_VARIETIES
