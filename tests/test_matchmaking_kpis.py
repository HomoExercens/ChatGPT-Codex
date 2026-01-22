from __future__ import annotations


def test_matchmaking_reason_and_human_match_rate(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    match = api_client.get("/api/matches/m_test_seed", headers=headers)
    assert match.status_code == 200
    payload = match.json()
    assert payload.get("opponent_type") == "bot"
    assert payload.get("matchmaking_reason") == "pool low, bot fallback"

    overview = api_client.get("/api/analytics/overview?mode=1v1", headers=headers)
    assert overview.status_code == 200
    summary = overview.json().get("summary", {})
    assert "human_matches" in summary
    assert "human_match_rate" in summary
    total = int(summary.get("matches_total") or 0)
    human = int(summary.get("human_matches") or 0)
    rate = float(summary.get("human_match_rate") or 0.0)
    assert 0 <= human <= total
    assert 0.0 <= rate <= 1.0
    if total:
        assert abs(rate - (human / total)) < 1e-12
