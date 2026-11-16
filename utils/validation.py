from collections.abc import Mapping
from dataclasses import dataclass

from utils.constants import (
    AROMAS, BALANCES, LOTS, REGIONS, SCORES, TECHNIQUES, variety_branch,
)


@dataclass(frozen=True)
class Evaluation:
    lot: int
    wine_type: str
    aromas: tuple[str, ...]
    technique: str
    fragrance: str | None
    variety_group: str | None
    grape: str
    region: str
    balance: str
    score: int


class InvalidEvaluation(ValueError):
    def __init__(self, fields: list[str]):
        self.fields = fields
        super().__init__(", ".join(fields))


def validate_evaluation(lot: int, answers: Mapping) -> Evaluation:
    if type(lot) is not int or lot not in LOTS:
        raise InvalidEvaluation(["Bortétel"])

    errors = []
    aromas = answers.get("aromas")
    if not isinstance(aromas, (list, tuple)) or not aromas or any(
        not isinstance(value, str) or value not in AROMAS for value in aromas
    ):
        errors.append("Jellemző aromacsoportok")

    field, branch_question, varieties = variety_branch(lot)
    branch = answers.get(field)
    grape = answers.get("grape")
    options = [
        ("technique", "Borkészítési technológia", TECHNIQUES),
        (field, branch_question.rstrip("?"), varieties),
        ("region", "Borvidék", REGIONS),
        ("balance", "Egyensúly", BALANCES),
    ]
    for key, label, choices in options:
        value = answers.get(key)
        if not isinstance(value, str) or value not in choices:
            errors.append(label)

    if isinstance(branch, str) and branch in varieties:
        if not isinstance(grape, str) or grape not in varieties[branch][1]:
            errors.append("Szőlőfajta")

    score = answers.get("score")
    if type(score) is not int or score not in SCORES:
        errors.append("Pontszám")
    if errors:
        raise InvalidEvaluation(errors)

    return Evaluation(
        lot=lot,
        wine_type=LOTS[lot],
        aromas=tuple(dict.fromkeys(aromas)),
        technique=answers["technique"],
        fragrance=branch if field == "fragrance" else None,
        variety_group=branch if field == "variety_group" else None,
        grape=grape,
        region=answers["region"],
        balance=answers["balance"],
        score=score,
    )
