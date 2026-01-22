from __future__ import annotations

from neuroleague_api.elo import update_elo


def test_elo_win_updates_as_expected() -> None:
    res = update_elo(
        rating_a=1000, rating_b=1000, score_a=1.0, games_played_a=0, games_played_b=0
    )
    assert res.new_a == 1020
    assert res.new_b == 980
    assert res.delta_a == 20
    assert res.delta_b == -20


def test_elo_draw_no_change_when_equal() -> None:
    res = update_elo(
        rating_a=1000, rating_b=1000, score_a=0.5, games_played_a=0, games_played_b=0
    )
    assert res.delta_a == 0
    assert res.delta_b == 0
