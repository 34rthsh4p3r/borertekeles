from collections import Counter

from utils.constants import AROMAS


def aroma_counts(records: list[dict]) -> Counter:
    counts = Counter({name: 0 for name in AROMAS})
    for record in records:
        counts.update(set(record["aromas"]))
    return counts


def answer_counts(records: list[dict], field: str) -> Counter:
    return Counter(record[field] for record in records if record[field] is not None)


def decimal_label(value: float | None) -> str:
    return f"{value:.2f}".replace(".", ",") if value is not None else "–"
