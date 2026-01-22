from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EloResult:
    new_a: int
    new_b: int
    delta_a: int
    delta_b: int


def _expected(rating_a: int, rating_b: int) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def update_elo(
    *,
    rating_a: int,
    rating_b: int,
    score_a: float,
    games_played_a: int,
    games_played_b: int,
) -> EloResult:
    k_a = 40 if games_played_a < 20 else 32
    k_b = 40 if games_played_b < 20 else 32

    expected_a = _expected(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a

    new_a = int(round(rating_a + k_a * (score_a - expected_a)))
    new_b = int(round(rating_b + k_b * (score_b - expected_b)))
    return EloResult(
        new_a=new_a, new_b=new_b, delta_a=new_a - rating_a, delta_b=new_b - rating_b
    )


def division_for_elo(elo: int) -> str:
    if elo >= 2400:
        return "Diamond II"
    if elo >= 2200:
        return "Diamond III"
    if elo >= 2000:
        return "Platinum I"
    if elo >= 1800:
        return "Platinum II"
    if elo >= 1600:
        return "Gold I"
    if elo >= 1400:
        return "Gold II"
    if elo >= 1200:
        return "Silver I"
    return "Bronze"
