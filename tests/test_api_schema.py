from __future__ import annotations


def test_openapi_contains_core_paths(api_client) -> None:
    schema = api_client.get("/api/openapi.json").json()
    paths = schema.get("paths", {})

    required_paths = [
        "/api/health",
        "/api/ready",
        "/api/metrics",
        "/api/events/track",
        "/api/experiments/assign",
        "/api/auth/guest",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/discord/start",
        "/api/auth/discord/callback",
        "/api/clips/feed",
        "/api/clips/{replay_id}/event",
        "/api/clips/{replay_id}/share_url",
        "/api/home/summary",
        "/api/blueprints",
        "/api/blueprints/{blueprint_id}/code",
        "/api/blueprints/{blueprint_id}/validate",
        "/api/blueprints/{blueprint_id}/submit",
        "/api/build_code/decode",
        "/api/build_code/import",
        "/api/challenges",
        "/api/challenges/{challenge_id}",
        "/api/challenges/{challenge_id}/accept",
        "/api/challenges/{challenge_id}/leaderboard",
        "/api/matches/queue",
        "/api/ranked/queue",
        "/api/matches/{match_id}",
        "/api/matches/{match_id}/replay",
        "/api/matches/{match_id}/highlights",
        "/api/matches/{match_id}/best_clip",
        "/api/matches/{match_id}/best_clip_jobs",
        "/api/replays/{replay_id}",
        "/api/replays/{replay_id}/sharecard",
        "/api/replays/{replay_id}/thumbnail",
        "/api/replays/{replay_id}/clip",
        "/api/analytics/overview",
        "/api/analytics/matchups",
        "/api/analytics/build-insights",
        "/api/analytics/version-compare",
        "/api/analytics/modifiers",
        "/api/analytics/portals",
        "/api/analytics/augments",
        "/api/meta/patch-notes",
        "/api/meta/modifiers",
        "/api/meta/portals",
        "/api/meta/augments",
        "/api/ops/balance/latest",
        "/api/ops/status",
        "/api/ops/reports",
        "/api/ops/reports/{report_id}/resolve",
        "/api/ops/moderation/hide_target",
        "/api/ops/moderation/soft_ban_user",
        "/api/ops/weekly",
        "/api/ops/weekly/override",
        "/api/ops/build_of_day",
        "/api/ops/build_of_day/override",
        "/api/ops/packs",
        "/api/ops/packs/candidate",
        "/api/ops/packs/promote",
        "/api/ops/metrics/summary",
        "/api/ops/metrics/funnel",
        "/api/ops/metrics/experiments",
        "/api/ops/metrics/shorts_variants",
        "/api/ops/preflight/latest",
        "/api/feed/activity",
        "/api/users/{user_id}/follow",
        "/api/training/runs",
        "/api/training/runs/{run_id}/to-blueprint",
        "/api/training/runs/{run_id}/benchmark",
    ]
    for p in required_paths:
        assert p in paths


def test_auth_login_home_blueprints_and_match_smoke(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = api_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user_id"] == "user_demo"

    home = api_client.get("/api/home/summary", headers=headers)
    assert home.status_code == 200
    assert home.json()["user"]["display_name"] == "Dr. Kairos"

    bps = api_client.get("/api/blueprints", headers=headers)
    assert bps.status_code == 200
    assert any(bp["id"] == "bp_demo_1v1" for bp in bps.json())

    match = api_client.get("/api/matches/m_test_seed", headers=headers)
    assert match.status_code == 200
    assert match.json()["id"] == "m_test_seed"

    highlights = api_client.get("/api/matches/m_test_seed/highlights", headers=headers)
    assert highlights.status_code == 200
    assert isinstance(highlights.json().get("highlights"), list)

    analytics = api_client.get("/api/analytics/overview", headers=headers)
    assert analytics.status_code == 200
    payload = analytics.json()
    assert "summary" in payload
    assert "elo_series" in payload
    assert "matchups" in payload

    feed = api_client.get(
        "/api/clips/feed?mode=1v1&sort=trending&limit=3", headers=headers
    )
    assert feed.status_code == 200
    feed_payload = feed.json()
    assert isinstance(feed_payload.get("items"), list)
