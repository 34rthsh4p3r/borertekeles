from collections import Counter
from statistics import mean, median

from utils.constants import AROMAS, SCORES


def aroma_counts(records: list[dict]) -> Counter:
    counts = Counter({name: 0 for name in AROMAS})
    for record in records:
        counts.update(set(record["aromas"]))
    return counts


def answer_counts(records: list[dict], field: str) -> Counter:
    return Counter(record[field] for record in records if record[field] is not None)


def score_statistics(records: list[dict]) -> tuple[dict, float | None, float | None]:
    scores = [record["score"] for record in records]
    counts = Counter(scores)
    return {score: counts[score] for score in SCORES}, mean(scores) if scores else None, median(scores) if scores else None


def decimal_label(value: float | None) -> str:
    return f"{value:.2f}".replace(".", ",") if value is not None else "–"
